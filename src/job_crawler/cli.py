"""Typer CLI for job-crawler."""

import typer
from rich.console import Console
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


if __name__ == "__main__":
    app()
