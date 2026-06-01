"""Typer CLI for job-crawler."""

import asyncio
import logging

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from job_crawler.db import repository

app = typer.Typer(name="job-crawler", help="Job search automation tool")
console = Console()


@app.command("db-init")
def db_init():
    """Initialize the SQLite database and apply schema."""
    db_path = repository.get_db_path()
    repository.init_db(db_path)
    console.print(f"[green]Database initialized:[/green] {db_path}")


@app.command("db-status")
def db_status():
    """Show database statistics."""
    db_path = repository.get_db_path()
    if not db_path.exists():
        console.print("[yellow]Database not found. Run [bold]job-crawler db-init[/bold] first.[/yellow]")
        raise typer.Exit(1)

    stats = repository.get_db_stats(db_path)

    table = Table(title="Job Crawler — Database Status", show_header=True, header_style="bold cyan")
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")

    table.add_row("Total Jobs", str(stats["total_jobs"]))
    table.add_row("Jobs Found Today", str(stats["jobs_today"]))
    table.add_row("Total Crawl Runs", str(stats["total_runs"]))
    table.add_row("Last Run At", stats["last_run_at"] or "—")
    table.add_row("Total Feedback", str(stats["total_feedback"]))
    table.add_row("Search Terms", str(stats["total_terms"]))
    table.add_row("Terms with Run Data", str(stats["terms_with_data"]))
    table.add_row("DB Path", str(db_path))

    console.print(table)


@app.command("run-search")
def run_search(
    dry_run: bool = typer.Option(False, "--dry-run", help="Fetch and normalize without saving to DB"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging"),
):
    """Run the job search pipeline: fetch, normalize, deduplicate, score, save."""
    from job_crawler.config import load_config
    from job_crawler.pipeline import run_pipeline

    log_level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    try:
        config = load_config()
    except Exception as e:
        console.print(f"[red]Config error:[/red] {e}")
        raise typer.Exit(1)

    if dry_run:
        console.print("[yellow]Dry run mode — results will not be saved[/yellow]")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
    ) as progress:
        progress.add_task("Running job search pipeline...", total=None)

        try:
            result = asyncio.run(run_pipeline(config, dry_run=dry_run))
        except Exception as e:
            console.print(f"[red]Pipeline error:[/red] {e}")
            raise typer.Exit(1)

    # Print summary
    console.print()
    console.print("[bold green]Run complete[/bold green]")
    console.print(f"  Sources searched: {', '.join(result.sources_searched)}")
    console.print(f"  Terms searched:   {result.terms_searched}")
    console.print(f"  Jobs fetched:     {result.jobs_fetched}")
    console.print(f"  Jobs new:         {len(result.jobs_new)}")
    console.print(f"  Exact duplicates: {result.jobs_exact_dup}")
    console.print(f"  Fuzzy duplicates: {result.jobs_fuzzy_dup}")

    if result.errors:
        console.print(f"\n[yellow]Warnings ({len(result.errors)}):[/yellow]")
        for err in result.errors[:5]:
            console.print(f"  {err}")

    if dry_run and result.jobs_new:
        console.print("\n[bold]Top 5 results (dry run preview):[/bold]")
        table = Table(show_header=True, header_style="bold")
        table.add_column("Score", width=6)
        table.add_column("Title", width=40)
        table.add_column("Company", width=25)
        table.add_column("Source", width=15)

        for job in sorted(result.jobs_new, key=lambda j: j.relevance_score, reverse=True)[:5]:
            table.add_row(
                f"{job.relevance_score:.0f}",
                job.title[:40],
                job.company[:25],
                job.source_site,
            )
        console.print(table)


@app.command("list-results")
def list_results(
    limit: int = typer.Option(20, "--limit", "-n", help="Number of results to show"),
    min_score: float = typer.Option(0.0, "--min-score", help="Minimum relevance score"),
    status: str = typer.Option("", "--status", help="Filter by status (new, reviewed, saved, rejected, applied)"),
    source: str = typer.Option("", "--source", help="Filter by source site"),
    today: bool = typer.Option(False, "--today", help="Show only today's results"),
):
    """List job results from the database."""
    from job_crawler.db import repository
    from datetime import date

    kwargs = dict(limit=limit, min_score=min_score)
    if status:
        kwargs["status"] = status
    if source:
        kwargs["source_site"] = source
    if today:
        kwargs["discovered_date"] = date.today().isoformat()

    jobs = repository.get_jobs(**kwargs)

    if not jobs:
        console.print("[yellow]No jobs found matching the filters.[/yellow]")
        return

    table = Table(title=f"Job Results ({len(jobs)} shown)", show_header=True, header_style="bold")
    table.add_column("Score", width=6, justify="right")
    table.add_column("Title", width=38, no_wrap=True)
    table.add_column("Company", width=22, no_wrap=True)
    table.add_column("Location", width=18, no_wrap=True)
    table.add_column("Salary", width=18)
    table.add_column("Source", width=12, no_wrap=True)
    table.add_column("Status", width=10)

    for job in jobs:
        # Color relevance score
        score_str = f"{job.relevance_score:.0f}"
        if job.relevance_score >= 70:
            score_display = f"[green]{score_str}[/green]"
        elif job.relevance_score >= 40:
            score_display = f"[yellow]{score_str}[/yellow]"
        else:
            score_display = f"[red]{score_str}[/red]"

        salary = ""
        if job.salary_min and job.salary_max:
            salary = f"${job.salary_min/1000:.0f}K–${job.salary_max/1000:.0f}K"
        elif job.salary_min:
            salary = f"${job.salary_min/1000:.0f}K+"

        location = job.location or ""
        if job.remote_status and job.remote_status.value != "unknown":
            location = f"{location} ({job.remote_status.value})" if location else job.remote_status.value

        table.add_row(
            score_display,
            job.title[:38],
            job.company[:22],
            location[:18],
            salary,
            job.source_site[:12],
            job.status,
        )

    console.print(table)


@app.command("give-feedback")
def give_feedback(
    job_id: str = typer.Argument(..., help="Job ID (from list-results)"),
    feedback: str = typer.Argument(..., help="Feedback type: strong_fit, possible_fit, not_relevant, too_junior, too_technical, wrong_industry, wrong_location, compensation_issue, already_applied, save_for_later, duplicate"),
    notes: str = typer.Option("", "--notes", "-n", help="Optional notes"),
):
    """Record feedback for a job."""
    from job_crawler.feedback import FeedbackManager
    from job_crawler.models import FeedbackType

    try:
        feedback_type = FeedbackType(feedback)
    except ValueError:
        valid = [t.value for t in FeedbackType]
        console.print(f"[red]Invalid feedback type: {feedback!r}[/red]")
        console.print(f"Valid types: {', '.join(valid)}")
        raise typer.Exit(1)

    mgr = FeedbackManager()
    try:
        mgr.record(job_id, feedback_type, notes or None)
        console.print(f"[green]✓[/green] Feedback recorded: {feedback_type.value} for job {job_id}")
    except Exception as e:
        console.print(f"[red]Error recording feedback:[/red] {e}")
        raise typer.Exit(1)


@app.command("generate-report")
def generate_report(
    date_str: str = typer.Option("", "--date", help="Date in YYYY-MM-DD format (default: today)"),
    top_n: int = typer.Option(30, "--top", help="Number of top jobs to include"),
    min_score: float = typer.Option(0.0, "--min-score", help="Minimum relevance score"),
    open_report: bool = typer.Option(False, "--open", help="Open the report in the default editor after generating"),
):
    """Generate a Markdown report for a given date."""
    from job_crawler.report import generate_report as gen_report
    from datetime import date
    import subprocess

    if date_str:
        try:
            report_date = date.fromisoformat(date_str)
        except ValueError:
            console.print(f"[red]Invalid date format: {date_str!r}. Use YYYY-MM-DD.[/red]")
            raise typer.Exit(1)
    else:
        report_date = date.today()

    try:
        report_path = gen_report(report_date=report_date, top_n=top_n, min_score=min_score)
        console.print(f"[green]✓[/green] Report written to: {report_path}")

        if open_report:
            subprocess.run(["open", str(report_path)], check=False)
    except Exception as e:
        console.print(f"[red]Error generating report:[/red] {e}")
        raise typer.Exit(1)


@app.command("term-stats")
def term_stats(
    limit: int = typer.Option(30, "--limit", "-n", help="Number of terms to show"),
    bottom: bool = typer.Option(False, "--bottom", help="Show lowest-performing terms instead"),
    category: str = typer.Option("", "--category", help="Filter by category"),
):
    """Show search term fitness scores and performance statistics."""
    from job_crawler.db import repository

    order = "fitness_score ASC" if bottom else "fitness_score DESC"
    terms = repository.get_term_stats(limit=limit, order_by=order)

    if category:
        terms = [t for t in terms if t.get("category", "").lower() == category.lower()]

    if not terms:
        console.print("[yellow]No term stats found. Run `job-crawler run-search` first.[/yellow]")
        return

    table = Table(title="Search Term Fitness", show_header=True, header_style="bold")
    table.add_column("Fitness", width=8, justify="right")
    table.add_column("Term", width=40)
    table.add_column("Category", width=20)
    table.add_column("Runs", width=6, justify="right")
    table.add_column("Jobs", width=6, justify="right")
    table.add_column("+", width=4, justify="right")
    table.add_column("-", width=4, justify="right")
    table.add_column("Next Run", width=12)

    for t in terms:
        fitness = t.get("fitness_score", 0.5)
        fitness_str = f"{fitness:.2f}"
        if fitness >= 0.7:
            fitness_display = f"[green]{fitness_str}[/green]"
        elif fitness >= 0.4:
            fitness_display = f"[yellow]{fitness_str}[/yellow]"
        else:
            fitness_display = f"[red]{fitness_str}[/red]"

        table.add_row(
            fitness_display,
            t.get("term", "")[:40],
            t.get("category", "")[:20],
            str(t.get("times_run", 0)),
            str(t.get("jobs_found", 0)),
            str(t.get("feedback_positive", 0)),
            str(t.get("feedback_negative", 0)),
            t.get("next_run_date", "") or "Today",
        )

    console.print(table)


if __name__ == "__main__":
    app()
