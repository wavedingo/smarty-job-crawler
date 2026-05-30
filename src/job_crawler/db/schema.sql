PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS jobs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id          TEXT    NOT NULL UNIQUE,
    source_site     TEXT    NOT NULL,
    source_url      TEXT,
    canonical_url   TEXT,
    title           TEXT    NOT NULL,
    company         TEXT    NOT NULL,
    location        TEXT,
    remote_status   TEXT    DEFAULT 'unknown',
    posted_date     TEXT,
    discovered_date TEXT    NOT NULL,
    application_deadline TEXT,
    salary_min      REAL,
    salary_max      REAL,
    bonus_or_equity_info TEXT,
    seniority_level TEXT,
    employment_type TEXT,
    industry        TEXT,
    job_function    TEXT,
    description_raw TEXT,
    description_clean TEXT,
    required_skills TEXT    DEFAULT '[]',
    preferred_skills TEXT   DEFAULT '[]',
    keywords_matched TEXT   DEFAULT '[]',
    score_signals   TEXT    DEFAULT '{}',
    relevance_score REAL    DEFAULT 0.0,
    quality_score   REAL    DEFAULT 0.0,
    duplicate_group_id INTEGER REFERENCES duplicate_groups(id),
    possible_cross_site_duplicate INTEGER DEFAULT 0,
    status          TEXT    DEFAULT 'new',
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_jobs_source_site ON jobs(source_site);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_relevance ON jobs(relevance_score DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_discovered ON jobs(discovered_date DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_company_title ON jobs(company, title);

CREATE TABLE IF NOT EXISTS feedback (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id          TEXT    NOT NULL REFERENCES jobs(job_id),
    feedback_type   TEXT    NOT NULL,
    notes           TEXT,
    created_at      TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_feedback_job_id ON feedback(job_id);
CREATE INDEX IF NOT EXISTS idx_feedback_type ON feedback(feedback_type);

CREATE TABLE IF NOT EXISTS job_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at      TEXT    NOT NULL,
    completed_at    TEXT,
    sources_searched TEXT   DEFAULT '[]',
    terms_searched  INTEGER DEFAULT 0,
    jobs_fetched    INTEGER DEFAULT 0,
    jobs_new        INTEGER DEFAULT 0,
    jobs_exact_dup  INTEGER DEFAULT 0,
    jobs_fuzzy_dup  INTEGER DEFAULT 0,
    status          TEXT    DEFAULT 'running',
    error_message   TEXT
);

CREATE TABLE IF NOT EXISTS duplicate_groups (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_job_id TEXT   REFERENCES jobs(job_id),
    detection_method TEXT,
    created_at      TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS sources (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT    NOT NULL UNIQUE,
    adapter_class   TEXT    NOT NULL,
    enabled         INTEGER DEFAULT 1,
    config_json     TEXT    DEFAULT '{}',
    last_run_at     TEXT,
    notes           TEXT
);

CREATE TABLE IF NOT EXISTS search_terms (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    term                TEXT    NOT NULL UNIQUE,
    category            TEXT,
    is_priority         INTEGER DEFAULT 0,
    is_boolean          INTEGER DEFAULT 0,
    enabled             INTEGER DEFAULT 1,
    times_run           INTEGER DEFAULT 0,
    jobs_found          INTEGER DEFAULT 0,
    feedback_positive   INTEGER DEFAULT 0,
    feedback_negative   INTEGER DEFAULT 0,
    fitness_score       REAL    DEFAULT 0.5,
    next_run_date       TEXT,
    last_run_at         TEXT
);

CREATE TABLE IF NOT EXISTS job_term_matches (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id      TEXT    NOT NULL REFERENCES jobs(job_id),
    term_id     INTEGER NOT NULL REFERENCES search_terms(id),
    run_id      INTEGER NOT NULL REFERENCES job_runs(id),
    created_at  TEXT    NOT NULL,
    UNIQUE (job_id, term_id, run_id)
);

CREATE INDEX IF NOT EXISTS idx_jtm_job_id ON job_term_matches(job_id);
CREATE INDEX IF NOT EXISTS idx_jtm_term_id ON job_term_matches(term_id);

CREATE TABLE IF NOT EXISTS scoring_adjustments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_type     TEXT    NOT NULL,
    signal_value    TEXT    NOT NULL,
    multiplier      REAL    NOT NULL DEFAULT 1.0,
    source_feedback_type TEXT,
    created_at      TEXT    NOT NULL
);
