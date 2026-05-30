"""Data access layer for job_crawler — raw SQLite, no ORM."""

import json
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

from job_crawler.models import Job, JobStatus, RemoteStatus, ScoringAdjustment, SearchTerm


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_db_path() -> Path:
    """Return the default DB path: <project_root>/data/jobs.db"""
    # This file lives at src/job_crawler/db/repository.py
    # Project root is three levels up
    project_root = Path(__file__).parent.parent.parent.parent
    return project_root / "data" / "jobs.db"


def get_connection(db_path: Path) -> sqlite3.Connection:
    """Open a SQLite connection with row_factory and foreign keys enabled."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _schema_path() -> Path:
    return Path(__file__).parent / "schema.sql"


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------

def _job_to_row(job: Job) -> dict:
    return {
        "job_id": job.job_id,
        "source_site": job.source_site,
        "source_url": job.source_url,
        "canonical_url": job.canonical_url,
        "title": job.title,
        "company": job.company,
        "location": job.location,
        "remote_status": job.remote_status.value,
        "posted_date": job.posted_date.isoformat() if job.posted_date else None,
        "discovered_date": job.discovered_date.isoformat(),
        "application_deadline": job.application_deadline.isoformat() if job.application_deadline else None,
        "salary_min": job.salary_min,
        "salary_max": job.salary_max,
        "bonus_or_equity_info": job.bonus_or_equity_info,
        "seniority_level": job.seniority_level,
        "employment_type": job.employment_type,
        "industry": job.industry,
        "job_function": job.job_function,
        "description_raw": job.description_raw,
        "description_clean": job.description_clean,
        "required_skills": json.dumps(job.required_skills),
        "preferred_skills": json.dumps(job.preferred_skills),
        "keywords_matched": json.dumps(job.keywords_matched),
        "score_signals": json.dumps(job.score_signals),
        "relevance_score": job.relevance_score,
        "quality_score": job.quality_score,
        "duplicate_group_id": job.duplicate_group_id,
        "possible_cross_site_duplicate": int(job.possible_cross_site_duplicate),
        "status": job.status.value,
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
    }


def _row_to_job(row: sqlite3.Row) -> Job:
    d = dict(row)
    return Job(
        job_id=d["job_id"],
        source_site=d["source_site"],
        source_url=d.get("source_url"),
        canonical_url=d.get("canonical_url"),
        title=d["title"],
        company=d["company"],
        location=d.get("location"),
        remote_status=RemoteStatus(d.get("remote_status", "unknown")),
        posted_date=date.fromisoformat(d["posted_date"]) if d.get("posted_date") else None,
        discovered_date=date.fromisoformat(d["discovered_date"]),
        application_deadline=date.fromisoformat(d["application_deadline"]) if d.get("application_deadline") else None,
        salary_min=d.get("salary_min"),
        salary_max=d.get("salary_max"),
        bonus_or_equity_info=d.get("bonus_or_equity_info"),
        seniority_level=d.get("seniority_level"),
        employment_type=d.get("employment_type"),
        industry=d.get("industry"),
        job_function=d.get("job_function"),
        description_raw=d.get("description_raw"),
        description_clean=d.get("description_clean"),
        required_skills=json.loads(d.get("required_skills") or "[]"),
        preferred_skills=json.loads(d.get("preferred_skills") or "[]"),
        keywords_matched=json.loads(d.get("keywords_matched") or "[]"),
        score_signals=json.loads(d.get("score_signals") or "{}"),
        relevance_score=d.get("relevance_score", 0.0),
        quality_score=d.get("quality_score", 0.0),
        duplicate_group_id=d.get("duplicate_group_id"),
        possible_cross_site_duplicate=bool(d.get("possible_cross_site_duplicate", 0)),
        status=JobStatus(d.get("status", "new")),
        created_at=datetime.fromisoformat(d["created_at"]),
        updated_at=datetime.fromisoformat(d["updated_at"]),
    )


def _row_to_search_term(row: sqlite3.Row) -> SearchTerm:
    d = dict(row)
    return SearchTerm(
        id=d.get("id"),
        term=d["term"],
        category=d.get("category"),
        is_priority=bool(d.get("is_priority", 0)),
        is_boolean=bool(d.get("is_boolean", 0)),
        enabled=bool(d.get("enabled", 1)),
        times_run=d.get("times_run", 0),
        jobs_found=d.get("jobs_found", 0),
        feedback_positive=d.get("feedback_positive", 0),
        feedback_negative=d.get("feedback_negative", 0),
        fitness_score=d.get("fitness_score", 0.5),
        next_run_date=date.fromisoformat(d["next_run_date"]) if d.get("next_run_date") else None,
        last_run_at=datetime.fromisoformat(d["last_run_at"]) if d.get("last_run_at") else None,
    )


def _row_to_scoring_adjustment(row: sqlite3.Row) -> ScoringAdjustment:
    d = dict(row)
    return ScoringAdjustment(
        id=d.get("id"),
        signal_type=d["signal_type"],
        signal_value=d["signal_value"],
        multiplier=d.get("multiplier", 1.0),
        source_feedback_type=d.get("source_feedback_type"),
        created_at=datetime.fromisoformat(d["created_at"]),
    )


# ---------------------------------------------------------------------------
# DB Init
# ---------------------------------------------------------------------------

def init_db(db_path: Path | None = None) -> None:
    """Create the database and apply schema.sql. Idempotent (IF NOT EXISTS)."""
    if db_path is None:
        db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    schema = _schema_path().read_text()
    conn = get_connection(db_path)
    try:
        conn.executescript(schema)
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------

def upsert_job(job: Job, db_path: Path | None = None) -> bool:
    """Insert job. Skip (return False) if job_id already exists. Return True if inserted."""
    if db_path is None:
        db_path = get_db_path()
    row = _job_to_row(job)
    sql = """
        INSERT OR IGNORE INTO jobs (
            job_id, source_site, source_url, canonical_url, title, company,
            location, remote_status, posted_date, discovered_date,
            application_deadline, salary_min, salary_max, bonus_or_equity_info,
            seniority_level, employment_type, industry, job_function,
            description_raw, description_clean, required_skills, preferred_skills,
            keywords_matched, score_signals, relevance_score, quality_score,
            duplicate_group_id, possible_cross_site_duplicate, status,
            created_at, updated_at
        ) VALUES (
            :job_id, :source_site, :source_url, :canonical_url, :title, :company,
            :location, :remote_status, :posted_date, :discovered_date,
            :application_deadline, :salary_min, :salary_max, :bonus_or_equity_info,
            :seniority_level, :employment_type, :industry, :job_function,
            :description_raw, :description_clean, :required_skills, :preferred_skills,
            :keywords_matched, :score_signals, :relevance_score, :quality_score,
            :duplicate_group_id, :possible_cross_site_duplicate, :status,
            :created_at, :updated_at
        )
    """
    conn = get_connection(db_path)
    try:
        cursor = conn.execute(sql, row)
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def get_jobs(
    status: str | None = None,
    source_site: str | None = None,
    min_score: float = 0.0,
    date: str | None = None,
    limit: int = 100,
    offset: int = 0,
    db_path: Path | None = None,
) -> list[Job]:
    """Fetch jobs with optional filters, ordered by relevance_score DESC."""
    if db_path is None:
        db_path = get_db_path()

    conditions = ["relevance_score >= :min_score"]
    params: dict = {"min_score": min_score, "limit": limit, "offset": offset}

    if status:
        conditions.append("status = :status")
        params["status"] = status
    if source_site:
        conditions.append("source_site = :source_site")
        params["source_site"] = source_site
    if date:
        conditions.append("discovered_date = :date")
        params["date"] = date

    where = " AND ".join(conditions)
    sql = f"""
        SELECT * FROM jobs
        WHERE {where}
        ORDER BY relevance_score DESC
        LIMIT :limit OFFSET :offset
    """
    conn = get_connection(db_path)
    try:
        rows = conn.execute(sql, params).fetchall()
        return [_row_to_job(r) for r in rows]
    finally:
        conn.close()


def get_job(job_id: str, db_path: Path | None = None) -> Job | None:
    """Fetch a single job by job_id."""
    if db_path is None:
        db_path = get_db_path()
    conn = get_connection(db_path)
    try:
        row = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        return _row_to_job(row) if row else None
    finally:
        conn.close()


def update_job_status(job_id: str, status: str, db_path: Path | None = None) -> None:
    if db_path is None:
        db_path = get_db_path()
    conn = get_connection(db_path)
    try:
        conn.execute(
            "UPDATE jobs SET status = ?, updated_at = ? WHERE job_id = ?",
            (status, datetime.utcnow().isoformat(), job_id),
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Feedback
# ---------------------------------------------------------------------------

def record_feedback(
    job_id: str,
    feedback_type: str,
    notes: str | None = None,
    db_path: Path | None = None,
) -> None:
    """Insert a feedback record."""
    if db_path is None:
        db_path = get_db_path()
    conn = get_connection(db_path)
    try:
        conn.execute(
            "INSERT INTO feedback (job_id, feedback_type, notes, created_at) VALUES (?, ?, ?, ?)",
            (job_id, feedback_type, notes, datetime.utcnow().isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Scoring Adjustments
# ---------------------------------------------------------------------------

def get_scoring_adjustments(db_path: Path | None = None) -> list[ScoringAdjustment]:
    if db_path is None:
        db_path = get_db_path()
    conn = get_connection(db_path)
    try:
        rows = conn.execute("SELECT * FROM scoring_adjustments ORDER BY id").fetchall()
        return [_row_to_scoring_adjustment(r) for r in rows]
    finally:
        conn.close()


def upsert_scoring_adjustment(adj: ScoringAdjustment, db_path: Path | None = None) -> None:
    if db_path is None:
        db_path = get_db_path()
    conn = get_connection(db_path)
    try:
        if adj.id is not None:
            conn.execute(
                """
                UPDATE scoring_adjustments
                SET signal_type=?, signal_value=?, multiplier=?,
                    source_feedback_type=?, created_at=?
                WHERE id=?
                """,
                (
                    adj.signal_type, adj.signal_value, adj.multiplier,
                    adj.source_feedback_type, adj.created_at.isoformat(), adj.id,
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO scoring_adjustments
                    (signal_type, signal_value, multiplier, source_feedback_type, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    adj.signal_type, adj.signal_value, adj.multiplier,
                    adj.source_feedback_type, adj.created_at.isoformat(),
                ),
            )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Job Runs
# ---------------------------------------------------------------------------

def start_run(db_path: Path | None = None) -> int:
    """Insert a new job_run record with status='running'. Return run ID."""
    if db_path is None:
        db_path = get_db_path()
    conn = get_connection(db_path)
    try:
        cursor = conn.execute(
            "INSERT INTO job_runs (started_at, status) VALUES (?, 'running')",
            (datetime.utcnow().isoformat(),),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def complete_run(
    run_id: int,
    jobs_fetched: int,
    jobs_new: int,
    jobs_exact_dup: int,
    jobs_fuzzy_dup: int,
    sources_searched: list[str],
    terms_searched: int,
    db_path: Path | None = None,
) -> None:
    if db_path is None:
        db_path = get_db_path()
    conn = get_connection(db_path)
    try:
        conn.execute(
            """
            UPDATE job_runs SET
                completed_at = ?,
                jobs_fetched = ?,
                jobs_new = ?,
                jobs_exact_dup = ?,
                jobs_fuzzy_dup = ?,
                sources_searched = ?,
                terms_searched = ?,
                status = 'completed'
            WHERE id = ?
            """,
            (
                datetime.utcnow().isoformat(),
                jobs_fetched, jobs_new, jobs_exact_dup, jobs_fuzzy_dup,
                json.dumps(sources_searched), terms_searched, run_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def fail_run(run_id: int, error: str, db_path: Path | None = None) -> None:
    if db_path is None:
        db_path = get_db_path()
    conn = get_connection(db_path)
    try:
        conn.execute(
            """
            UPDATE job_runs SET
                completed_at = ?,
                status = 'failed',
                error_message = ?
            WHERE id = ?
            """,
            (datetime.utcnow().isoformat(), error, run_id),
        )
        conn.commit()
    finally:
        conn.close()


def get_runs(limit: int = 20, db_path: Path | None = None) -> list[dict]:
    if db_path is None:
        db_path = get_db_path()
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM job_runs ORDER BY started_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Search Terms
# ---------------------------------------------------------------------------

def get_todays_terms(
    max_secondary: int = 20,
    db_path: Path | None = None,
) -> tuple[list[SearchTerm], list[SearchTerm], list[SearchTerm]]:
    """
    Returns (priority_terms, boolean_terms, secondary_terms_for_today).

    Priority terms: is_priority=1, enabled=1 (always run)
    Boolean terms: is_boolean=1, enabled=1 (always run)
    Secondary terms: enabled=1, is_priority=0, is_boolean=0,
                    (next_run_date IS NULL OR next_run_date <= today),
                    ordered by: times_run=0 first (discovery), then fitness_score DESC,
                    limit max_secondary
    """
    if db_path is None:
        db_path = get_db_path()
    today = date.today().isoformat()
    conn = get_connection(db_path)
    try:
        priority_rows = conn.execute(
            "SELECT * FROM search_terms WHERE is_priority=1 AND enabled=1"
        ).fetchall()
        boolean_rows = conn.execute(
            "SELECT * FROM search_terms WHERE is_boolean=1 AND enabled=1"
        ).fetchall()
        secondary_rows = conn.execute(
            """
            SELECT * FROM search_terms
            WHERE enabled=1 AND is_priority=0 AND is_boolean=0
              AND (next_run_date IS NULL OR next_run_date <= ?)
            ORDER BY
                CASE WHEN times_run = 0 THEN 0 ELSE 1 END ASC,
                fitness_score DESC
            LIMIT ?
            """,
            (today, max_secondary),
        ).fetchall()
        return (
            [_row_to_search_term(r) for r in priority_rows],
            [_row_to_search_term(r) for r in boolean_rows],
            [_row_to_search_term(r) for r in secondary_rows],
        )
    finally:
        conn.close()


def load_terms_from_config(terms_config: dict, db_path: Path | None = None) -> int:
    """
    Seed/sync search_terms table from the YAML config.
    Insert terms that don't exist yet (by exact term text).
    Don't overwrite fitness_score or run stats on existing terms.
    Returns count of newly inserted terms.
    """
    if db_path is None:
        db_path = get_db_path()

    to_insert: list[dict] = []

    # Priority terms
    for term in terms_config.get("priority_terms", []):
        to_insert.append({
            "term": term,
            "category": "priority",
            "is_priority": 1,
            "is_boolean": 0,
        })

    # Boolean searches
    for item in terms_config.get("boolean_searches", []):
        if item.get("enabled", True):
            to_insert.append({
                "term": item["query"],
                "category": "boolean",
                "is_priority": 0,
                "is_boolean": 1,
            })

    # Category terms
    for category_name, category_data in terms_config.get("categories", {}).items():
        if not category_data.get("enabled", True):
            continue
        for term in category_data.get("terms", []):
            to_insert.append({
                "term": term,
                "category": category_name,
                "is_priority": 0,
                "is_boolean": 0,
            })

    conn = get_connection(db_path)
    inserted = 0
    try:
        for item in to_insert:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO search_terms
                    (term, category, is_priority, is_boolean, enabled)
                VALUES (?, ?, ?, ?, 1)
                """,
                (item["term"], item["category"], item["is_priority"], item["is_boolean"]),
            )
            inserted += cursor.rowcount
        conn.commit()
    finally:
        conn.close()

    return inserted


def record_job_term_matches(
    job_ids: list[str],
    term_ids: list[int],
    run_id: int,
    db_path: Path | None = None,
) -> None:
    """Record that these jobs were found by these terms in this run."""
    if db_path is None:
        db_path = get_db_path()
    now = datetime.utcnow().isoformat()
    conn = get_connection(db_path)
    try:
        for job_id in job_ids:
            for term_id in term_ids:
                conn.execute(
                    "INSERT OR IGNORE INTO job_term_matches (job_id, term_id, run_id, created_at) VALUES (?, ?, ?, ?)",
                    (job_id, term_id, run_id, now),
                )
        conn.commit()
    finally:
        conn.close()


def _next_run_date_from_fitness(fitness_score: float, times_run: int, pos: int, neg: int) -> str:
    """Compute next_run_date based on fitness score."""
    today = date.today()
    if pos == 0 and neg == 0:
        # No feedback yet — run every 2 days
        return (today + timedelta(days=2)).isoformat()
    if fitness_score >= 0.70:
        delta = 1
    elif fitness_score >= 0.40:
        delta = 3
    elif fitness_score >= 0.20:
        delta = 7
    else:
        delta = 14
    return (today + timedelta(days=delta)).isoformat()


def update_term_after_run(
    term_id: int,
    jobs_found: int,
    db_path: Path | None = None,
) -> None:
    """Increment times_run, add jobs_found, set last_run_at, compute next_run_date."""
    if db_path is None:
        db_path = get_db_path()
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT times_run, jobs_found, fitness_score, feedback_positive, feedback_negative FROM search_terms WHERE id=?",
            (term_id,),
        ).fetchone()
        if not row:
            return
        new_times_run = row["times_run"] + 1
        new_jobs_found = row["jobs_found"] + jobs_found
        next_run = _next_run_date_from_fitness(
            row["fitness_score"], new_times_run,
            row["feedback_positive"], row["feedback_negative"],
        )
        conn.execute(
            """
            UPDATE search_terms SET
                times_run = ?,
                jobs_found = ?,
                last_run_at = ?,
                next_run_date = ?
            WHERE id = ?
            """,
            (new_times_run, new_jobs_found, datetime.utcnow().isoformat(), next_run, term_id),
        )
        conn.commit()
    finally:
        conn.close()


def update_term_fitness(
    term_id: int,
    is_positive: bool,
    db_path: Path | None = None,
) -> None:
    """
    Increment feedback_positive or feedback_negative.
    Recalculate fitness_score = positive / (positive + negative).
    Update next_run_date based on new fitness score.
    """
    if db_path is None:
        db_path = get_db_path()
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT feedback_positive, feedback_negative, times_run FROM search_terms WHERE id=?",
            (term_id,),
        ).fetchone()
        if not row:
            return
        pos = row["feedback_positive"] + (1 if is_positive else 0)
        neg = row["feedback_negative"] + (0 if is_positive else 1)
        total = pos + neg
        fitness = pos / total if total > 0 else 0.5
        next_run = _next_run_date_from_fitness(fitness, row["times_run"], pos, neg)
        conn.execute(
            """
            UPDATE search_terms SET
                feedback_positive = ?,
                feedback_negative = ?,
                fitness_score = ?,
                next_run_date = ?
            WHERE id = ?
            """,
            (pos, neg, fitness, next_run, term_id),
        )
        conn.commit()
    finally:
        conn.close()


def get_term_stats(
    limit: int = 50,
    order_by: str = "fitness_score DESC",
    db_path: Path | None = None,
) -> list[dict]:
    """Return term stats for CLI display and dashboard."""
    if db_path is None:
        db_path = get_db_path()
    # Allowlist to prevent SQL injection from order_by
    allowed_order = {
        "fitness_score DESC", "fitness_score ASC",
        "times_run DESC", "jobs_found DESC",
        "term ASC", "term DESC",
        "last_run_at DESC",
    }
    if order_by not in allowed_order:
        order_by = "fitness_score DESC"
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            f"SELECT * FROM search_terms ORDER BY {order_by} LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# DB Stats
# ---------------------------------------------------------------------------

def get_db_stats(db_path: Path | None = None) -> dict:
    """Return dict with: total_jobs, jobs_today, total_runs, last_run_at,
    total_feedback, total_terms, terms_with_data"""
    if db_path is None:
        db_path = get_db_path()
    today = date.today().isoformat()
    conn = get_connection(db_path)
    try:
        total_jobs = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        jobs_today = conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE discovered_date = ?", (today,)
        ).fetchone()[0]
        total_runs = conn.execute("SELECT COUNT(*) FROM job_runs").fetchone()[0]
        last_run_row = conn.execute(
            "SELECT started_at FROM job_runs ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        last_run_at = last_run_row[0] if last_run_row else None
        total_feedback = conn.execute("SELECT COUNT(*) FROM feedback").fetchone()[0]
        total_terms = conn.execute("SELECT COUNT(*) FROM search_terms").fetchone()[0]
        terms_with_data = conn.execute(
            "SELECT COUNT(*) FROM search_terms WHERE times_run > 0"
        ).fetchone()[0]
        return {
            "total_jobs": total_jobs,
            "jobs_today": jobs_today,
            "total_runs": total_runs,
            "last_run_at": last_run_at,
            "total_feedback": total_feedback,
            "total_terms": total_terms,
            "terms_with_data": terms_with_data,
        }
    finally:
        conn.close()
