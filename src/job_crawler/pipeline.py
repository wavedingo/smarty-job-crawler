"""Pipeline: orchestrates the full run-search flow."""

import asyncio
import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from job_crawler.adapters import get_adapter
from job_crawler.config import AppConfig
from job_crawler.db import repository
from job_crawler.deduplication import DuplicateDetector, make_compound_key
from job_crawler.models import Job, RawJob, SearchTerm
from job_crawler.normalizer import Normalizer
from job_crawler.scoring import ScoringEngine

logger = logging.getLogger(__name__)


@dataclass
class RunResult:
    run_id: int
    jobs_new: list[Job] = field(default_factory=list)
    jobs_exact_dup: int = 0
    jobs_fuzzy_dup: int = 0
    jobs_fetched: int = 0
    terms_searched: int = 0
    sources_searched: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


async def run_pipeline(
    config: AppConfig,
    db_path: Path | None = None,
    dry_run: bool = False,
) -> RunResult:
    """
    Full run-search pipeline:

    1. Select today's terms (priority + boolean + fitness-based secondary)
    2. Fetch from all enabled sources concurrently
    3. Normalize raw results to Job objects
    4. Exact deduplication (skip already-seen job_ids / compound keys)
    5. Fuzzy cross-site duplicate detection
    6. Score each new job (relevance + quality + feedback multipliers)
    7. Persist to DB, record job_term_matches, update term stats
    8. Return RunResult
    """
    run_id = repository.start_run(db_path)
    result = RunResult(run_id=run_id)

    try:
        # ------------------------------------------------------------------
        # Step 1: Load/sync terms from config, then get today's selection
        # ------------------------------------------------------------------
        repository.load_terms_from_config(
            {
                "priority_terms": config.priority_terms,
                "categories": config.categories,
                "boolean_searches": config.boolean_searches,
            },
            db_path,
        )
        priority_terms, boolean_terms, secondary_terms = repository.get_todays_terms(
            max_secondary=config.max_terms_per_run, db_path=db_path
        )
        all_terms: list[SearchTerm] = priority_terms + boolean_terms + secondary_terms
        term_texts = [t.term for t in all_terms]
        result.terms_searched = len(all_terms)

        logger.info(
            "Running search: %d terms (%d priority, %d boolean, %d secondary)",
            len(all_terms), len(priority_terms), len(boolean_terms), len(secondary_terms),
        )

        # ------------------------------------------------------------------
        # Step 2: Fetch from all enabled sources concurrently
        # ------------------------------------------------------------------
        enabled_sources = {
            name: src for name, src in config.sources.items() if src.enabled
        }
        result.sources_searched = list(enabled_sources.keys())

        async def fetch_from_source(source_name: str, src_config) -> list[RawJob]:
            try:
                adapter = get_adapter(src_config.adapter)
                raw = await adapter.fetch_all(term_texts, src_config.config)
                logger.info("[%s] fetched %d raw results", source_name, len(raw))
                return raw
            except Exception as e:
                msg = f"[{source_name}] fetch failed: {e}"
                logger.error(msg)
                result.errors.append(msg)
                return []

        tasks = [
            fetch_from_source(name, src_cfg)
            for name, src_cfg in enabled_sources.items()
        ]
        all_raw_lists = await asyncio.gather(*tasks, return_exceptions=False)
        all_raw: list[RawJob] = [r for sublist in all_raw_lists for r in sublist]
        result.jobs_fetched = len(all_raw)

        # ------------------------------------------------------------------
        # Step 3: Normalize — returns (Job, search_term) pairs
        # ------------------------------------------------------------------
        normalizer = Normalizer(config)
        pairs = normalizer.normalize_many(all_raw)
        jobs = [j for j, _ in pairs]
        job_search_terms: dict[str, str | None] = {j.job_id: st for j, st in pairs}
        logger.info("Normalized %d/%d raw results", len(jobs), len(all_raw))

        # ------------------------------------------------------------------
        # Step 4: Exact deduplication
        # ------------------------------------------------------------------
        if not dry_run:
            new_jobs: list[Job] = []
            compound_keys_seen: set[str] = set()

            for job in jobs:
                ck = make_compound_key(job.company, job.title, job.location)
                if ck in compound_keys_seen:
                    result.jobs_exact_dup += 1
                    continue
                compound_keys_seen.add(ck)
                inserted = repository.upsert_job(job, db_path)
                if inserted:
                    new_jobs.append(job)
                else:
                    result.jobs_exact_dup += 1
        else:
            # Dry run — deduplicate in memory only
            new_jobs = []
            seen_ids: set[str] = set()
            for job in jobs:
                if job.job_id not in seen_ids:
                    new_jobs.append(job)
                    seen_ids.add(job.job_id)

        # ------------------------------------------------------------------
        # Step 5: Fuzzy cross-site duplicate detection
        # ------------------------------------------------------------------
        if new_jobs and not dry_run:
            recent_jobs = repository.get_jobs(limit=500, db_path=db_path)
            new_job_ids = {j.job_id for j in new_jobs}
            existing_older = [j for j in recent_jobs if j.job_id not in new_job_ids]

            detector = DuplicateDetector()
            fuzzy_matches = detector.find_fuzzy_duplicates(new_jobs, existing_older)
            group_map = detector.group_cross_site_duplicates(fuzzy_matches)
            result.jobs_fuzzy_dup = len(group_map)

            for job in new_jobs:
                if job.job_id in group_map:
                    job.possible_cross_site_duplicate = True

        # ------------------------------------------------------------------
        # Step 6: Score each new job
        # ------------------------------------------------------------------
        adjustments = repository.get_scoring_adjustments(db_path) if not dry_run else []
        scorer = ScoringEngine(config.scoring, priority_terms=config.priority_terms)

        for job in new_jobs:
            score_result = scorer.score(job)
            job.relevance_score = scorer.apply_feedback_multipliers(
                score_result.relevance_score, job, adjustments
            )
            job.quality_score = score_result.quality_score
            job.score_signals = score_result.signals

        result.jobs_new = new_jobs

        # ------------------------------------------------------------------
        # Step 7: Persist scores, term matches, term stats
        # ------------------------------------------------------------------
        if not dry_run:
            # Update scores via repository method (no raw SQL in pipeline)
            if new_jobs:
                repository.update_job_scores(new_jobs, db_path)

            # Record term → job relationships (per search_term, not cartesian product)
            # Build a mapping from term text → term_id
            term_by_text: dict[str, int] = {
                t.term: t.id for t in all_terms if t.id is not None
            }
            # For each new job, find which term surfaced it
            job_to_term: list[tuple[str, int]] = []
            for job in new_jobs:
                term_text = job_search_terms.get(job.job_id)
                if term_text and term_text in term_by_text:
                    job_to_term.append((job.job_id, term_by_text[term_text]))

            # Record matches individually (ATS adapters set search_term=None — omitted)
            if job_to_term:
                db = db_path or repository.get_db_path()
                now = datetime.now(timezone.utc).isoformat()
                with sqlite3.connect(str(db)) as conn:
                    conn.executemany(
                        "INSERT OR IGNORE INTO job_term_matches (job_id, term_id, run_id, created_at) VALUES (?,?,?,?)",
                        [(jid, tid, run_id, now) for jid, tid in job_to_term],
                    )
                    conn.commit()

            # Update per-term stats
            for term in all_terms:
                if term.id is not None:
                    repository.update_term_after_run(term.id, len(new_jobs), db_path)

            # Complete the run record
            repository.complete_run(
                run_id,
                jobs_fetched=result.jobs_fetched,
                jobs_new=len(result.jobs_new),
                jobs_exact_dup=result.jobs_exact_dup,
                jobs_fuzzy_dup=result.jobs_fuzzy_dup,
                sources_searched=result.sources_searched,
                terms_searched=result.terms_searched,
                db_path=db_path,
            )

        logger.info(
            "Run complete: %d new, %d exact dup, %d fuzzy dup",
            len(new_jobs), result.jobs_exact_dup, result.jobs_fuzzy_dup,
        )

    except Exception as e:
        logger.error("Pipeline failed: %s", e, exc_info=True)
        result.errors.append(str(e))
        if not dry_run:
            repository.fail_run(run_id, str(e), db_path)
        raise

    return result
