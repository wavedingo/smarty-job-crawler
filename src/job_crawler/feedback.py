"""Feedback manager: stores feedback and propagates score adjustments."""

import logging
import sqlite3
from datetime import datetime, timezone

from job_crawler.models import FeedbackType, Job, ScoringAdjustment
from job_crawler.db import repository

logger = logging.getLogger(__name__)

POSITIVE_TYPES = {
    FeedbackType.STRONG_FIT,
    FeedbackType.POSSIBLE_FIT,
    FeedbackType.SAVE_FOR_LATER,
}
NEGATIVE_TYPES = {
    FeedbackType.NOT_RELEVANT,
    FeedbackType.TOO_JUNIOR,
    FeedbackType.TOO_TECHNICAL,
    FeedbackType.WRONG_INDUSTRY,
    FeedbackType.WRONG_LOCATION,
    FeedbackType.COMPENSATION_ISSUE,
}

# Map feedback types to job status transitions
STATUS_MAP = {
    FeedbackType.SAVE_FOR_LATER: "saved",
    FeedbackType.ALREADY_APPLIED: "applied",
    FeedbackType.NOT_RELEVANT: "rejected",
    FeedbackType.TOO_JUNIOR: "rejected",
    FeedbackType.TOO_TECHNICAL: "rejected",
    FeedbackType.WRONG_INDUSTRY: "rejected",
    FeedbackType.WRONG_LOCATION: "rejected",
    FeedbackType.COMPENSATION_ISSUE: "rejected",
    FeedbackType.STRONG_FIT: "reviewed",
    FeedbackType.POSSIBLE_FIT: "reviewed",
}


class FeedbackManager:
    def __init__(self, db_path=None):
        self.db_path = db_path

    def record(
        self,
        job_id: str,
        feedback_type: FeedbackType,
        notes: str | None = None,
    ) -> None:
        """
        Record feedback for a job.  Side effects:
        1. Insert feedback row
        2. Update job status
        3. Create/update scoring adjustment for company + domain
        4. Update term fitness for all terms that found this job
        """
        # 1. Record feedback
        repository.record_feedback(job_id, feedback_type.value, notes, self.db_path)

        # 2. Update job status
        new_status = STATUS_MAP.get(feedback_type)
        if new_status:
            repository.update_job_status(job_id, new_status, self.db_path)

        # 3. Create scoring adjustments
        job = repository.get_job(job_id, self.db_path)
        if job:
            self._create_scoring_adjustment(job, feedback_type)

        # 4. Update term fitness
        is_positive = feedback_type in POSITIVE_TYPES
        is_negative = feedback_type in NEGATIVE_TYPES
        if is_positive or is_negative:
            self._update_term_fitness(job_id, is_positive)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _create_scoring_adjustment(self, job: Job, feedback_type: FeedbackType) -> None:
        """Derive and store a scoring adjustment from feedback."""
        if feedback_type in POSITIVE_TYPES:
            multiplier = 1.15
        elif feedback_type in NEGATIVE_TYPES:
            multiplier = 0.85
        else:
            return  # DUPLICATE, ALREADY_APPLIED don't affect scoring

        now = datetime.now(timezone.utc)

        # Company-level adjustment
        if job.company:
            adj = ScoringAdjustment(
                signal_type="company",
                signal_value=job.company,
                multiplier=multiplier,
                source_feedback_type=feedback_type.value,
                created_at=now,
            )
            repository.upsert_scoring_adjustment(adj, self.db_path)

        # Domain-level adjustments based on keywords found
        for kw in job.keywords_matched[:3]:  # top 3 matched keywords
            adj = ScoringAdjustment(
                signal_type="domain",
                signal_value=kw,
                multiplier=multiplier,
                source_feedback_type=feedback_type.value,
                created_at=now,
            )
            repository.upsert_scoring_adjustment(adj, self.db_path)

    def _update_term_fitness(self, job_id: str, is_positive: bool) -> None:
        """Update fitness for all search terms that found this job."""
        try:
            db = self.db_path or repository.get_db_path()
            with sqlite3.connect(str(db)) as conn:
                rows = conn.execute(
                    "SELECT term_id FROM job_term_matches WHERE job_id = ?",
                    (job_id,),
                ).fetchall()

            for (term_id,) in rows:
                repository.update_term_fitness(term_id, is_positive, self.db_path)

            if rows:
                logger.debug(
                    "Updated fitness for %d terms (job %s, positive=%s)",
                    len(rows), job_id, is_positive,
                )
        except Exception as e:
            logger.warning(
                "Could not update term fitness for job %s: %s", job_id, e
            )
