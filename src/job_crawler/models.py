"""Pydantic v2 models and enums for job_crawler."""

from enum import Enum
from datetime import date, datetime
from pydantic import BaseModel


class RemoteStatus(str, Enum):
    REMOTE = "remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"
    UNKNOWN = "unknown"


class JobStatus(str, Enum):
    NEW = "new"
    REVIEWED = "reviewed"
    SAVED = "saved"
    REJECTED = "rejected"
    APPLIED = "applied"


class FeedbackType(str, Enum):
    STRONG_FIT = "strong_fit"
    POSSIBLE_FIT = "possible_fit"
    NOT_RELEVANT = "not_relevant"
    DUPLICATE = "duplicate"
    TOO_JUNIOR = "too_junior"
    TOO_TECHNICAL = "too_technical"
    WRONG_INDUSTRY = "wrong_industry"
    WRONG_LOCATION = "wrong_location"
    COMPENSATION_ISSUE = "compensation_issue"
    ALREADY_APPLIED = "already_applied"
    SAVE_FOR_LATER = "save_for_later"


class Job(BaseModel):
    job_id: str
    source_site: str
    source_url: str | None = None
    canonical_url: str | None = None
    title: str
    company: str
    location: str | None = None
    remote_status: RemoteStatus = RemoteStatus.UNKNOWN
    posted_date: date | None = None
    discovered_date: date
    application_deadline: date | None = None
    salary_min: float | None = None
    salary_max: float | None = None
    bonus_or_equity_info: str | None = None
    seniority_level: str | None = None
    employment_type: str | None = None
    industry: str | None = None
    job_function: str | None = None
    description_raw: str | None = None
    description_clean: str | None = None
    required_skills: list[str] = []
    preferred_skills: list[str] = []
    keywords_matched: list[str] = []
    score_signals: dict[str, float] = {}
    relevance_score: float = 0.0
    quality_score: float = 0.0
    duplicate_group_id: int | None = None
    possible_cross_site_duplicate: bool = False
    status: JobStatus = JobStatus.NEW
    created_at: datetime
    updated_at: datetime


class RawJob(BaseModel):
    """Unvalidated output from a source adapter before normalization."""
    source_site: str
    external_id: str | None = None
    url: str
    title: str
    company: str
    search_term: str | None = None   # which search term found this job
    raw_data: dict = {}


class FeedbackRecord(BaseModel):
    id: int | None = None
    job_id: str
    feedback_type: FeedbackType
    notes: str | None = None
    created_at: datetime


class JobRun(BaseModel):
    id: int | None = None
    started_at: datetime
    completed_at: datetime | None = None
    sources_searched: list[str] = []
    terms_searched: int = 0
    jobs_fetched: int = 0
    jobs_new: int = 0
    jobs_exact_dup: int = 0
    jobs_fuzzy_dup: int = 0
    status: str = "running"
    error_message: str | None = None


class SearchTerm(BaseModel):
    id: int | None = None
    term: str
    category: str | None = None
    is_priority: bool = False
    is_boolean: bool = False
    enabled: bool = True
    times_run: int = 0
    jobs_found: int = 0
    feedback_positive: int = 0
    feedback_negative: int = 0
    fitness_score: float = 0.5
    next_run_date: date | None = None
    last_run_at: datetime | None = None


class ScoringAdjustment(BaseModel):
    id: int | None = None
    signal_type: str   # company | domain | title_keyword
    signal_value: str
    multiplier: float = 1.0
    source_feedback_type: str | None = None
    created_at: datetime
