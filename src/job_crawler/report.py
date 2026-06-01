"""Generate dated Markdown reports for job search results."""

import json
from datetime import date
from pathlib import Path

from job_crawler.db import repository
from job_crawler.models import Job


def _get_reports_dir() -> Path:
    """Returns <project_root>/data/reports/, creating it if needed."""
    db_path = repository.get_db_path()
    reports_dir = db_path.parent / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    return reports_dir


def _format_salary(job: Job) -> str:
    if job.salary_min and job.salary_max:
        return f"${job.salary_min:,.0f}–${job.salary_max:,.0f}"
    elif job.salary_min:
        return f"${job.salary_min:,.0f}+"
    elif job.salary_max:
        return f"Up to ${job.salary_max:,.0f}"
    return "Not listed"


def _format_remote(job: Job) -> str:
    return job.remote_status.value.capitalize() if job.remote_status else "Unknown"


def generate_report(
    report_date: date | None = None,
    top_n: int = 30,
    min_score: float = 0.0,
    db_path: Path | None = None,
) -> Path:
    """
    Generate a Markdown report for the given date (defaults to today).
    Returns the path to the written report file.
    """
    report_date = report_date or date.today()
    date_str = report_date.isoformat()

    # Fetch jobs discovered today, sorted by relevance
    jobs = repository.get_jobs(
        discovered_date=date_str,
        min_score=min_score,
        limit=top_n,
        db_path=db_path,
    )

    # Also get run stats for today's summary
    runs = repository.get_runs(limit=5, db_path=db_path)
    today_runs = [r for r in runs if r.get("started_at", "").startswith(date_str)]

    lines = [
        f"# Job Search Report — {date_str}",
        "",
        "## Summary",
        "",
    ]

    if today_runs:
        latest = today_runs[0]
        lines += [
            f"- **Jobs found today:** {latest.get('jobs_new', 0)} new, {latest.get('jobs_exact_dup', 0)} duplicates skipped",
            f"- **Sources searched:** {', '.join(json.loads(latest.get('sources_searched', '[]')))}",
            f"- **Terms searched:** {latest.get('terms_searched', 0)}",
            f"- **Run status:** {latest.get('status', 'unknown')}",
        ]
    else:
        lines.append(f"- No runs found for {date_str}")

    lines += [
        "",
        f"## Top {len(jobs)} Recommendations",
        "",
    ]

    if not jobs:
        lines.append("_No jobs found for this date. Run `job-crawler run-search` to fetch new results._")

    for rank, job in enumerate(jobs, start=1):
        salary = _format_salary(job)
        remote = _format_remote(job)
        dup_warning = " ⚠️ Possible duplicate" if job.possible_cross_site_duplicate else ""

        # Parse score signals for explanation
        try:
            signals = json.loads(job.score_signals) if isinstance(job.score_signals, str) else (job.score_signals or {})
            top_signals = sorted(signals.items(), key=lambda x: abs(x[1]), reverse=True)[:3]
            why = "; ".join(f"{k.replace('_', ' ').title()}: {v:+.0f}pts" for k, v in top_signals)
        except Exception:
            why = "Score breakdown unavailable"

        apply_url = job.canonical_url or job.source_url or ""

        lines += [
            f"### {rank}. {job.title} — {job.company}",
            "",
            f"**Relevance:** {job.relevance_score:.0f}/100 | **Quality:** {job.quality_score:.0f}/100{dup_warning}",
            f"**Location:** {job.location or 'Not specified'} | **Remote:** {remote}",
            f"**Salary:** {salary}",
            f"**Source:** {job.source_site} | [Apply Here]({apply_url})" if apply_url else f"**Source:** {job.source_site}",
            f"**Why recommended:** {why}",
            f"**Status:** {job.status}",
            "",
            "---",
            "",
        ]

    content = "\n".join(lines)
    report_path = _get_reports_dir() / f"{date_str}.md"
    report_path.write_text(content, encoding="utf-8")
    return report_path
