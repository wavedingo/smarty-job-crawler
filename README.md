# Job Search Crawler

A local-first job search automation tool that crawls multiple job boards, scores results by relevance, deduplicates cross-site postings, and learns from your feedback over time to surface better matches.

## Overview

Job Search Crawler runs configurable search terms across Indeed, Dice, Greenhouse/Lever ATS boards, Welcome to the Jungle, and Google Careers. Each job is normalized, deduplicated, and scored using a weighted relevance model that accounts for title match, seniority level, domain keyword density, and description quality. You review results in a local FastAPI dashboard or via CLI, provide feedback (strong fit, not relevant, etc.), and the tool adapts — boosting companies and keywords associated with good fits, and burying terms that keep returning noise.

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) — fast Python package manager

## Setup

```bash
git clone https://github.com/yourname/job_search_crawler.git
cd job_search_crawler

# Install dependencies (creates .venv automatically)
uv sync

# Initialize the database
uv run job-crawler db-init
```

After `db-init`, the SQLite database is created at `data/jobs.db` and all search terms from the config are seeded into it.

## Configuration

There are three YAML files in `config/`:

### `config/sources.yaml`

Controls which job boards are active and their adapter settings. Each source has an `enabled` flag. The `global.max_terms_per_run` key limits how many secondary terms run per crawl session (priority and boolean terms always run regardless).

Key sources: `indeed`, `dice`, `anthropic`, `openai`, `xai`, `welcome_to_the_jungle`, `google_careers`.

### `config/search_terms.yaml`

Three sections:

- **`priority_terms`** — always run on every crawl (limit 10 terms). Edit these to match your target roles.
- **`boolean_searches`** — complex boolean queries run on every crawl. Use these for AND/OR combinations.
- **`categories`** — secondary term pools organized by domain. The crawler selects up to `max_terms_per_run` of these per session, prioritizing terms with high fitness scores.

### `config/scoring.yaml`

Controls the relevance scoring model:

- **`relevance_weights`** — point values for each scoring signal (title match, seniority, keyword density, etc.)
- **`seniority_keywords`** — terms that trigger the seniority signal (VP, Director, Head of, etc.)
- **`domain_buckets`** — keyword groups with weights; matched keywords drive the `keyword_density` and `domain_fit` signals
- **`negative_keywords`** — terms that penalize a job's relevance score
- **`quality_weights`** — point values for quality signals (salary present, description length, ATS link, freshness)

## Running a Search

```bash
# Run a full crawl (all enabled sources, today's selected terms)
uv run job-crawler run-search

# Dry run — fetch and score but do not write to the database
uv run job-crawler run-search --dry-run

# Run with verbose output
uv run job-crawler run-search --verbose
```

The crawler logs progress to the console and writes all new jobs to `data/jobs.db`.

## Reviewing Results

**Web dashboard** — starts a local FastAPI server:

```bash
uv run job-crawler serve
# Open http://localhost:8000
```

The dashboard shows jobs sorted by relevance score with filtering by status, source, and score threshold. The `/terms` route shows search term fitness stats.

**CLI listing:**

```bash
# Show top results (default: top 20 by relevance score)
uv run job-crawler list-results

# Filter by status
uv run job-crawler list-results --status new
uv run job-crawler list-results --status saved

# Filter by minimum score
uv run job-crawler list-results --min-score 60
```

**Generate a report:**

```bash
# HTML report saved to data/reports/
uv run job-crawler generate-report

# Specify output path
uv run job-crawler generate-report --output /path/to/report.html
```

## Giving Feedback

Feedback trains the scoring model. Positive feedback boosts the company and matched keywords by 1.15×; negative feedback applies a 0.85× penalty.

```bash
# Record feedback for a job by its ID
uv run job-crawler give-feedback <job_id> <feedback_type>

# Examples
uv run job-crawler give-feedback abc123def456 strong_fit
uv run job-crawler give-feedback abc123def456 not_relevant
```

Available feedback types:

| Type | Effect |
|------|--------|
| `strong_fit` | Positive — boosts company + keywords |
| `possible_fit` | Positive — boosts company + keywords |
| `save_for_later` | Positive — marks job as saved |
| `not_relevant` | Negative — penalizes company + keywords |
| `too_junior` | Negative — penalizes company + keywords |
| `too_technical` | Negative — penalizes company + keywords |
| `wrong_industry` | Negative — penalizes company + keywords |
| `wrong_location` | Negative — penalizes company + keywords |
| `compensation_issue` | Negative — penalizes company + keywords |
| `already_applied` | Neutral — marks job as applied, no score effect |
| `duplicate` | Neutral — marks job as duplicate, no score effect |

Feedback can also be submitted from the web dashboard using the action buttons on each job card.

## Viewing Term Fitness

Term fitness is a 0.0–1.0 score representing how often a search term leads to jobs you rate positively. Terms with high fitness run more frequently; low-fitness terms run less often.

```bash
# Show term stats sorted by fitness (default)
uv run job-crawler term-stats

# Sort by times run
uv run job-crawler term-stats --order times_run
```

In the dashboard, visit `/terms` for a full table with fitness scores, run counts, and next scheduled date.

## Scheduling (macOS)

Use launchd to run the crawler automatically on weekday mornings at 8:00 AM.

```bash
# 1. Find the job-crawler executable path (run inside your venv)
source .venv/bin/activate
which job-crawler
```

Copy that path, then edit `launchd/com.jobcrawler.daily.plist` and replace `/path/to/venv/bin/job-crawler` with the actual path.

```bash
# 2. Load the plist into launchd
launchctl load ~/Projects/job_search_crawler/launchd/com.jobcrawler.daily.plist

# 3. Verify it is registered
launchctl list com.jobcrawler.daily

# 4. Trigger manually to test it works
launchctl start com.jobcrawler.daily

# 5. Check output logs
tail -f ~/Projects/job_search_crawler/data/logs/run.log
tail -f ~/Projects/job_search_crawler/data/logs/run.err

# 6. To unload (stop scheduling)
launchctl unload ~/Projects/job_search_crawler/launchd/com.jobcrawler.daily.plist
```

Logs are written to `data/logs/run.log` (stdout) and `data/logs/run.err` (stderr).

## Source Notes

**Tier 1 (full adapter, keyword search):** Indeed, Dice, Greenhouse ATS boards (Anthropic, OpenAI), Lever ATS boards (xAI).

**Tier 2 (browse/discovery only):** Welcome to the Jungle, Google Careers — these adapters fetch recent postings without keyword filtering.

**Not yet supported:** LinkedIn, Glassdoor, Wellfound. These platforms block automated access; integration would require official API access or a paid scraping proxy.
