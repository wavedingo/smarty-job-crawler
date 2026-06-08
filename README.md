# Smarty Job Crawler

A local-first job search automation tool. It crawls multiple job boards daily, normalises every posting into a structured format, deduplicates cross-site listings, scores results by relevance to your target roles, and learns from your feedback over time to surface better matches.

---

## How it works

1. **Crawl** — fetches jobs from configured sources (Greenhouse ATS boards, Playwright-based scrapers, direct APIs)
2. **Normalise** — extracts title, company, location, salary, remote status, seniority, and skills from every posting
3. **Deduplicate** — skips exact duplicates and flags likely cross-site duplicates
4. **Score** — weights each job on title match, seniority, domain keyword density, and description quality
5. **Learn** — your feedback (strong fit / not relevant / etc.) adjusts future scores and controls how often each search term runs

---

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) — fast Python package manager (`brew install uv`)

---

## Setup

```bash
git clone https://github.com/wavedingo/smarty-job-crawler.git
cd smarty-job-crawler

# Install Python dependencies
uv sync

# Install Chromium for Playwright (used to scrape OpenAI and Perplexity)
uv run playwright install chromium

# Initialise the database
uv run job-crawler db-init
```

`db-init` creates `data/jobs.db` and seeds all search terms from `config/search_terms.yaml` into it.

---

## Running a search

```bash
# Full crawl — fetch, score, and save to database
uv run job-crawler run-search

# Preview only — fetch and score but do not write anything
uv run job-crawler run-search --dry-run

# Verbose logging
uv run job-crawler run-search --verbose
```

The first run takes 30–60 seconds because Playwright launches Chromium to scrape OpenAI and Perplexity. Subsequent runs are faster (those results are cached per session).

---

## Reviewing results

### Web dashboard

```bash
uv run job-crawler serve
# Open http://localhost:8080
```

The dashboard has four views:

| Route | Description |
|---|---|
| `/` | Today's jobs, sorted by relevance score |
| `/jobs` | Full list with filters (status, source, min score, text search) |
| `/runs` | History of every crawl run |
| `/terms` | Search term fitness scores and scheduling info |

Click any feedback button on a job row to record your opinion — the row updates in place without a page reload.

### CLI

```bash
# Show top 20 results by relevance score
uv run job-crawler list-results

# Filter by status or source
uv run job-crawler list-results --status new --today
uv run job-crawler list-results --status saved
uv run job-crawler list-results --min-score 60

# Generate a dated Markdown report in data/reports/
uv run job-crawler generate-report

# Open the report after generating (macOS)
uv run job-crawler generate-report --open
```

---

## Giving feedback

Feedback adjusts the scoring model and search term scheduling. Record it from the dashboard (click the buttons on each job row) or from the CLI:

```bash
uv run job-crawler give-feedback <job_id> <type>

# Examples
uv run job-crawler give-feedback abc123 strong_fit
uv run job-crawler give-feedback abc123 not_relevant
```

Job IDs are shown in `list-results` output.

### Feedback types

| Type | Score effect | Status change |
|---|---|---|
| `strong_fit` | Boosts company + keywords ×1.15 | → reviewed |
| `possible_fit` | Boosts company + keywords ×1.15 | → reviewed |
| `save_for_later` | Boosts company + keywords ×1.15 | → saved |
| `not_relevant` | Penalises company + keywords ×0.85 | → rejected |
| `too_junior` | Penalises company + keywords ×0.85 | → rejected |
| `too_technical` | Penalises company + keywords ×0.85 | → rejected |
| `wrong_industry` | Penalises company + keywords ×0.85 | → rejected |
| `wrong_location` | Penalises company + keywords ×0.85 | → rejected |
| `compensation_issue` | Penalises company + keywords ×0.85 | → rejected |
| `already_applied` | None | → applied |
| `duplicate` | None | no change |

Feedback also propagates back to every search term that originally surfaced the job, adjusting how frequently that term runs in future crawls.

---

## Search term fitness

Each search term earns a **fitness score** (0.0–1.0) based on the quality of jobs it surfaces. Positive feedback raises the score; negative feedback lowers it. Score determines run frequency:

| Fitness | Runs every |
|---|---|
| ≥ 0.70 | Daily |
| 0.40–0.69 | 3 days |
| 0.20–0.39 | Weekly |
| < 0.20 | 14 days |

New terms start at 0.50 (neutral) and run every 2 days until they have enough data.

```bash
# Show highest-scoring terms
uv run job-crawler term-stats

# Show lowest-scoring terms
uv run job-crawler term-stats --bottom
```

---

## Configuration

All configuration lives in `config/`. Files are plain YAML — edit them directly.

### `config/sources.yaml`

Controls which job boards are active. Set `enabled: true/false` to toggle sources. The `global.max_terms_per_run` key caps how many secondary search terms run per session (priority and boolean terms always run).

To add a new Greenhouse company:
```yaml
shopify:
  adapter: greenhouse
  enabled: true
  config:
    board_slug: shopify   # from https://job-boards.greenhouse.io/{slug}
```

To add a new Ashby company:
```yaml
notion:
  adapter: ashby
  enabled: true
  config:
    org_id: notion        # from https://jobs.ashbyhq.com/{org_id}
```

### `config/search_terms.yaml`

- **`priority_terms`** — 10 terms that run on every crawl, regardless of fitness score
- **`boolean_searches`** — complex AND/OR queries (run against Indeed when it becomes available again)
- **`categories`** — pools of secondary terms, selected by fitness score each run

### `config/scoring.yaml`

- **`relevance_weights`** — point values for each signal (title match, seniority, keyword density, etc.)
- **`seniority_keywords`** — terms that trigger the seniority signal
- **`domain_buckets`** — keyword groups by domain (ecommerce, media/podcast, partnerships, etc.)
- **`negative_keywords`** — terms that penalise a job's relevance score
- **`quality_weights`** — point values for quality signals (salary, description length, ATS link, freshness)

---

## Scheduling on macOS

The crawler can run automatically on weekday mornings at 8 AM using launchd.

**1. Find the `job-crawler` binary path:**

```bash
source .venv/bin/activate
which job-crawler
# e.g. /Users/yourname/Projects/smarty-job-crawler/.venv/bin/job-crawler
```

**2. Update the plist with that path:**

Edit `launchd/com.jobcrawler.daily.plist` and replace `/path/to/venv/bin/job-crawler` with the path from step 1.

**3. Load and start:**

```bash
launchctl load ~/Projects/smarty-job-crawler/launchd/com.jobcrawler.daily.plist

# Test it manually
launchctl start com.jobcrawler.daily

# Check logs
tail -f ~/Projects/smarty-job-crawler/data/logs/run.log
```

**4. To stop scheduling:**

```bash
launchctl unload ~/Projects/smarty-job-crawler/launchd/com.jobcrawler.daily.plist
```

---

## Active sources

| Source | Method | Notes |
|---|---|---|
| **Anthropic** | Greenhouse public API | Reliable — official ATS board |
| **xAI** | Greenhouse public API | Reliable — official ATS board |
| **OpenAI** | Playwright DOM scraper | OpenAI has no public job API; Playwright renders their careers page |
| **Perplexity** | Playwright + API intercept | Perplexity's `/api/jobs` requires browser cookies; Playwright handles this automatically |

### Adding more sources

**Greenhouse** — find the board slug from the company's careers URL (`job-boards.greenhouse.io/{slug}`) and add it to `sources.yaml`. No code changes needed.

**Ashby** — find the org ID from `jobs.ashbyhq.com/{org_id}` and add it to `sources.yaml`. No code changes needed.

**Lever** — find the company slug from `jobs.lever.co/{slug}` and add it to `sources.yaml`. No code changes needed.

### Currently disabled sources

| Source | Reason |
|---|---|
| Indeed | IP-level 403 block — RSS feed no longer accessible without browser session |
| Dice | Undocumented internal API now blocked |
| Welcome to the Jungle | API endpoint gone |
| Google Careers | Undocumented endpoint gone |
| LinkedIn / Glassdoor / Wellfound | Require authentication; aggressive anti-bot systems |

---

## CLI reference

```
job-crawler db-init           Initialise the database
job-crawler db-status         Show database statistics
job-crawler run-search        Run the full crawl pipeline
job-crawler serve             Start the web dashboard (default: http://localhost:8080)
job-crawler list-results      Print top jobs as a terminal table
job-crawler give-feedback     Record feedback for a job by ID
job-crawler generate-report   Write a Markdown report to data/reports/
job-crawler term-stats        Show search term fitness scores
```

Run `job-crawler <command> --help` for options on any command.

---

## Data storage

Everything is stored locally in `data/jobs.db` (SQLite). The database is not committed to the repo (`.gitignore`d). Reports are written to `data/reports/`. Logs (when running via launchd) go to `data/logs/`.
