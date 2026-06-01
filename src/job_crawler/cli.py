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


if __name__ == "__main__":
    app()
