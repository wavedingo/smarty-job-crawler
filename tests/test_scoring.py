import pytest
from job_crawler.scoring import ScoringEngine
from job_crawler.models import ScoringAdjustment
from datetime import datetime, timezone

def test_exact_title_match_gets_full_points(sample_job, sample_scoring_config):
    scorer = ScoringEngine(sample_scoring_config, priority_terms=["VP eCommerce"])
    result = scorer.score(sample_job)
    assert "title_exact_match" in result.signals
    assert result.signals["title_exact_match"] == 30

def test_seniority_match_detected(sample_job, sample_scoring_config):
    scorer = ScoringEngine(sample_scoring_config, priority_terms=[])
    result = scorer.score(sample_job)
    assert "seniority_match" in result.signals
    assert result.signals["seniority_match"] == 20

def test_negative_keywords_reduce_score(sample_scoring_config):
    from job_crawler.models import Job, RemoteStatus
    from datetime import date
    now = datetime.now(timezone.utc)
    job = Job(
        job_id="neg_test",
        source_site="test",
        source_url="https://example.com",
        title="Junior Coordinator",
        company="Acme",
        discovered_date=date.today(),
        description_clean="intern coordinator entry-level associate role",
        created_at=now, updated_at=now,
    )
    scorer = ScoringEngine(sample_scoring_config, priority_terms=[])
    result = scorer.score(job)
    assert "negative_signals" in result.signals
    assert result.signals["negative_signals"] < 0

def test_score_clamped_to_100(sample_job, sample_scoring_config):
    # Even with all signals firing, score should not exceed 100
    scorer = ScoringEngine(sample_scoring_config, priority_terms=["VP eCommerce"])
    result = scorer.score(sample_job)
    assert result.relevance_score <= 100.0
    assert result.relevance_score >= 0.0

def test_feedback_multiplier_boosts_score(sample_job, sample_scoring_config):
    scorer = ScoringEngine(sample_scoring_config, priority_terms=[])
    base_result = scorer.score(sample_job)
    base = base_result.relevance_score

    adj = ScoringAdjustment(
        signal_type="company",
        signal_value="Acme Corp",
        multiplier=1.15,
        created_at=datetime.now(timezone.utc),
    )
    boosted = scorer.apply_feedback_multipliers(base, sample_job, [adj])
    assert boosted > base

def test_feedback_multiplier_reduces_score(sample_job, sample_scoring_config):
    scorer = ScoringEngine(sample_scoring_config, priority_terms=[])
    base_result = scorer.score(sample_job)
    base = base_result.relevance_score

    adj = ScoringAdjustment(
        signal_type="company",
        signal_value="Acme Corp",
        multiplier=0.85,
        created_at=datetime.now(timezone.utc),
    )
    reduced = scorer.apply_feedback_multipliers(base, sample_job, [adj])
    assert reduced < base

def test_explanation_returns_top_3_signals(sample_job, sample_scoring_config):
    scorer = ScoringEngine(sample_scoring_config, priority_terms=["VP eCommerce"])
    result = scorer.score(sample_job)
    parts = result.explanation.split(";")
    assert len(parts) <= 3
    assert len(result.explanation) > 0

def test_keywords_matched_populated(sample_job, sample_scoring_config):
    scorer = ScoringEngine(sample_scoring_config, priority_terms=[])
    scorer.score(sample_job)
    # Side-effect: job.keywords_matched should be populated
    assert isinstance(sample_job.keywords_matched, list)
