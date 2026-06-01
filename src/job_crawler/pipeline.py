"""Pipeline: orchestrates the full run-search flow."""

import asyncio
import json
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
        # Step 3: Normalize
        # ------------------------------------------------------------------
        normalizer = Normalizer(config)
        jobs = normalizer.normalize_many(all_raw)
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
            db = db_path or repository.get_db_path()
            with sqlite3.connect(str(db)) as conn:
                for job in new_jobs:
                    conn.execute(
                        """
                        UPDATE jobs
                        SET relevance_score = ?,
                            quality_score = ?,
                            score_signals = ?,
                            keywords_matched = ?,
                            possible_cross_site_duplicate = ?,
                            updated_at = ?
                        WHERE job_id = ?
                        """,
                        (
                            job.relevance_score,
                            job.quality_score,
                            json.dumps(job.score_signals),
                            json.dumps(job.keywords_matched),
                            1 if job.possible_cross_site_duplicate else 0,
                            datetime.now(timezone.utc).isoformat(),
                            job.job_id,
                        ),
                    )
                conn.commit()

            # Record term → job relationships
            new_job_ids_list = [j.job_id for j in new_jobs]
            term_ids = [t.id for t in all_terms if t.id is not None]
            if new_job_ids_list and term_ids:
                repository.record_job_term_matches(
                    new_job_ids_list, term_ids, run_id, db_path
                )

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
