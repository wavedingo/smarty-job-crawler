"""FastAPI web dashboard for job_crawler."""

import asyncio
import json
import logging
from datetime import date
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from job_crawler.db import repository
from job_crawler.feedback import FeedbackManager
from job_crawler.models import FeedbackType

logger = logging.getLogger(__name__)

# Locate templates dir relative to this file:
# src/job_crawler/server.py -> src/job_crawler/ -> src/ -> project_root -> templates/
_TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates"

app = FastAPI(title="Job Crawler Dashboard")
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


# ─── Template helpers ────────────────────────────────────────────────────────

def _format_salary(job) -> str:
    if job.salary_min and job.salary_max:
        return f"${job.salary_min:,.0f}–${job.salary_max:,.0f}"
    elif job.salary_min:
        return f"${job.salary_min:,.0f}+"
    elif job.salary_max:
        return f"Up to ${job.salary_max:,.0f}"
    return ""


def _score_color(score: float) -> str:
    if score >= 70:
        return "success"   # Bootstrap green
    elif score >= 40:
        return "warning"   # Bootstrap yellow
    return "danger"        # Bootstrap red


def _explain_signals(score_signals) -> str:
    try:
        signals = json.loads(score_signals) if isinstance(score_signals, str) else (score_signals or {})
        top = sorted(signals.items(), key=lambda x: abs(x[1]), reverse=True)[:3]
        return "; ".join(f"{k.replace('_', ' ').title()}: {v:+.0f}pts" for k, v in top)
    except Exception:
        return ""


# Register helpers as Jinja2 globals
@app.on_event("startup")
async def setup_template_globals():
    templates.env.globals["format_salary"] = _format_salary
    templates.env.globals["score_color"] = _score_color
    templates.env.globals["explain_signals"] = _explain_signals
    templates.env.globals["FeedbackType"] = FeedbackType
    templates.env.filters["from_json"] = json.loads


# ─── Routes ──────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request, page: int = 1):
    """Today's jobs, sorted by relevance."""
    per_page = 50
    today = date.today().isoformat()
    jobs = repository.get_jobs(
        discovered_date=today,
        limit=per_page,
        offset=(page - 1) * per_page,
    )
    stats = repository.get_db_stats()
    return templates.TemplateResponse(request, "index.html", {
        "jobs": jobs,
        "stats": stats,
        "today": today,
        "page": page,
        "feedback_types": [ft.value for ft in FeedbackType],
    })


@app.get("/jobs", response_class=HTMLResponse)
async def jobs_list(
    request: Request,
    status: str = "",
    source: str = "",
    min_score: float = 0.0,
    q: str = "",
    page: int = 1,
):
    """Full job list with filters."""
    per_page = 50
    kwargs = dict(
        limit=per_page,
        offset=(page - 1) * per_page,
        min_score=min_score,
    )
    if status:
        kwargs["status"] = status
    if source:
        kwargs["source_site"] = source

    jobs = repository.get_jobs(**kwargs)

    # Basic text search filter (client-side since DB doesn't have FTS yet)
    if q:
        q_lower = q.lower()
        jobs = [j for j in jobs if q_lower in j.title.lower() or q_lower in j.company.lower()]

    return templates.TemplateResponse(request, "jobs.html", {
        "jobs": jobs,
        "status_filter": status,
        "source_filter": source,
        "min_score": min_score,
        "q": q,
        "page": page,
        "feedback_types": [ft.value for ft in FeedbackType],
        "statuses": ["new", "reviewed", "saved", "rejected", "applied"],
    })


@app.get("/runs", response_class=HTMLResponse)
async def runs(request: Request):
    """Run history."""
    run_list = repository.get_runs(limit=30)
    return templates.TemplateResponse(request, "runs.html", {
        "runs": run_list,
    })


@app.get("/terms", response_class=HTMLResponse)
async def terms(request: Request, sort: str = "desc"):
    """Term fitness dashboard."""
    order = "fitness_score ASC" if sort == "asc" else "fitness_score DESC"
    term_list = repository.get_term_stats(limit=200, order_by=order)
    return templates.TemplateResponse(request, "terms.html", {
        "terms": term_list,
        "sort": sort,
    })


@app.post("/api/jobs/{job_id}/feedback", response_class=HTMLResponse)
async def record_feedback(
    request: Request,
    job_id: str,
    feedback_type: str = Form(...),
    notes: str = Form(""),
):
    """Record feedback. Returns updated job_row.html partial for HTMX swap."""
    try:
        ft = FeedbackType(feedback_type)
        mgr = FeedbackManager()
        mgr.record(job_id, ft, notes or None)
    except (ValueError, Exception) as e:
        logger.warning("Feedback error for %s: %s", job_id, e)

    job = repository.get_job(job_id)
    if job is None:
        return HTMLResponse("<tr><td colspan='8'>Job not found</td></tr>", status_code=404)

    return templates.TemplateResponse(request, "partials/job_row.html", {
        "job": job,
        "feedback_types": [ft.value for ft in FeedbackType],
        "active_feedback": feedback_type,
    })


@app.post("/api/jobs/{job_id}/status", response_class=HTMLResponse)
async def update_status(
    request: Request,
    job_id: str,
    status: str = Form(...),
):
    """Update job status."""
    repository.update_job_status(job_id, status)
    job = repository.get_job(job_id)
    if job is None:
        return HTMLResponse("Job not found", status_code=404)
    return templates.TemplateResponse(request, "partials/job_row.html", {
        "job": job,
        "feedback_types": [ft.value for ft in FeedbackType],
        "active_feedback": "",
    })


@app.post("/api/run-search", response_class=HTMLResponse)
async def trigger_run(request: Request):
    """Trigger a pipeline run in the background."""
    from job_crawler.config import load_config
    from job_crawler.pipeline import run_pipeline

    async def _run():
        try:
            config = load_config()
            await run_pipeline(config)
            logger.info("Background run completed")
        except Exception as e:
            logger.error("Background run failed: %s", e)

    asyncio.create_task(_run())
    return HTMLResponse(
        '<div class="alert alert-info">Run started in background. Refresh in a minute.</div>'
    )
