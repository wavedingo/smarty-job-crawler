import pytest
import sqlite3
from pathlib import Path
from datetime import datetime, timezone, date

from job_crawler.db import repository
from job_crawler.models import (
    Job, RawJob, FeedbackType, JobStatus, RemoteStatus, SearchTerm
)
from job_crawler.config import load_config, ScoringConfig, DomainBucket

@pytest.fixture
def tmp_db(tmp_path):
    """In-memory SQLite DB (file-based temp for fixture sharing)."""
    db_path = tmp_path / "test.db"
    repository.init_db(db_path)
    return db_path

@pytest.fixture
def sample_job():
    now = datetime.now(timezone.utc)
    return Job(
        job_id="test_job_001",
        source_site="indeed",
        source_url="https://example.com/job/1",
        canonical_url="https://example.com/job/1",
        title="VP eCommerce",
        company="Acme Corp",
        location="New York, NY",
        remote_status=RemoteStatus.HYBRID,
        discovered_date=date.today(),
        description_clean="We are looking for a VP of eCommerce to lead our marketplace strategy. P&L ownership required. Amazon and Walmart experience preferred.",
        relevance_score=85.0,
        quality_score=70.0,
        created_at=now,
        updated_at=now,
    )

@pytest.fixture
def sample_scoring_config():
    return ScoringConfig(
        relevance_weights={
            "title_exact_match": 30,
            "title_partial_match": 15,
            "keyword_density": 25,
            "seniority_match": 20,
            "domain_fit": 15,
            "negative_signal_per_hit": -5,
            "negative_signal_cap": -15,
        },
        seniority_keywords=["VP", "Vice President", "Director", "Head of", "General Manager", "GM"],
        domain_buckets={
            "ecommerce": DomainBucket(weight=1.0, keywords=["ecommerce", "marketplace", "DTC", "omnichannel", "Amazon", "Walmart"]),
            "media_podcast": DomainBucket(weight=1.0, keywords=["podcast", "audio", "creator economy"]),
        },
        negative_keywords=["junior", "intern", "coordinator", "software engineer"],
        quality_weights={
            "salary_present": 20,
            "description_length_full": 20,
            "description_length_partial": 10,
            "direct_ats_link": 15,
            "fresh_posting_14d": 15,
            "fresh_posting_30d": 8,
            "low_duplicate_risk": 15,
            "known_company": 15,
        },
        location_neutral=True,
        preferred_remote_statuses=[],
    )
