import pytest
from datetime import datetime, timezone, date
from job_crawler.feedback import FeedbackManager, POSITIVE_TYPES, NEGATIVE_TYPES
from job_crawler.models import FeedbackType, Job, RemoteStatus
from job_crawler.db import repository

@pytest.fixture
def job_in_db(tmp_db, sample_job):
    """Insert sample_job into tmp_db and return (db_path, job)."""
    repository.upsert_job(sample_job, tmp_db)
    return tmp_db, sample_job

def test_feedback_recorded_in_db(job_in_db):
    db_path, job = job_in_db
    mgr = FeedbackManager(db_path=db_path)
    mgr.record(job.job_id, FeedbackType.STRONG_FIT)

    # Verify feedback row exists
    import sqlite3
    with sqlite3.connect(str(db_path)) as conn:
        rows = conn.execute(
            "SELECT feedback_type FROM feedback WHERE job_id = ?", (job.job_id,)
        ).fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "strong_fit"

def test_strong_fit_creates_positive_adjustment(job_in_db):
    db_path, job = job_in_db
    # Pre-score the job to populate keywords_matched
    from job_crawler.scoring import ScoringEngine
    from job_crawler.config import ScoringConfig, DomainBucket
    config = ScoringConfig(
        relevance_weights={"title_exact_match": 30, "keyword_density": 25, "seniority_match": 20, "domain_fit": 15, "title_partial_match": 15, "negative_signal_per_hit": -5, "negative_signal_cap": -15},
        seniority_keywords=["VP"],
        domain_buckets={"ecommerce": DomainBucket(weight=1.0, keywords=["marketplace", "Amazon"])},
        negative_keywords=[],
        quality_weights={},
        location_neutral=True,
        preferred_remote_statuses=[],
    )
    scorer = ScoringEngine(config, priority_terms=["VP eCommerce"])
    scorer.score(job)  # Sets job.keywords_matched as side-effect

    mgr = FeedbackManager(db_path=db_path)
    mgr.record(job.job_id, FeedbackType.STRONG_FIT)

    adjustments = repository.get_scoring_adjustments(db_path)
    company_adjs = [a for a in adjustments if a.signal_type == "company"]
    assert len(company_adjs) >= 1
    assert company_adjs[0].multiplier == 1.15

def test_not_relevant_creates_negative_adjustment(job_in_db):
    db_path, job = job_in_db
    mgr = FeedbackManager(db_path=db_path)
    mgr.record(job.job_id, FeedbackType.NOT_RELEVANT)

    adjustments = repository.get_scoring_adjustments(db_path)
    company_adjs = [a for a in adjustments if a.signal_type == "company"]
    assert len(company_adjs) >= 1
    assert company_adjs[0].multiplier == 0.85

def test_feedback_updates_job_status(job_in_db):
    db_path, job = job_in_db
    mgr = FeedbackManager(db_path=db_path)
    mgr.record(job.job_id, FeedbackType.SAVE_FOR_LATER)

    updated = repository.get_job(job.job_id, db_path)
    assert updated.status == "saved"

def test_positive_types_defined():
    assert FeedbackType.STRONG_FIT in POSITIVE_TYPES
    assert FeedbackType.POSSIBLE_FIT in POSITIVE_TYPES
    assert FeedbackType.NOT_RELEVANT not in POSITIVE_TYPES

def test_negative_types_defined():
    assert FeedbackType.NOT_RELEVANT in NEGATIVE_TYPES
    assert FeedbackType.TOO_JUNIOR in NEGATIVE_TYPES
    assert FeedbackType.STRONG_FIT not in NEGATIVE_TYPES
