"""Scoring engine: relevance + quality scoring for Job objects."""

import logging
from dataclasses import dataclass

from job_crawler.config import ScoringConfig
from job_crawler.models import Job, ScoringAdjustment

logger = logging.getLogger(__name__)


@dataclass
class ScoreResult:
    relevance_score: float
    quality_score: float
    signals: dict[str, float]
    explanation: str  # top-3 signals as human-readable string


class ScoringEngine:
    def __init__(self, config: ScoringConfig, priority_terms: list[str] | None = None):
        self.config = config
        self.priority_terms = [t.lower() for t in (priority_terms or [])]

    def score(self, job: Job) -> ScoreResult:
        """Score a job for relevance and quality. Returns ScoreResult."""
        relevance, signals = self._score_relevance(job)
        quality = self._score_quality(job)
        explanation = self._explain(signals)

        return ScoreResult(
            relevance_score=round(min(100.0, max(0.0, relevance)), 1),
            quality_score=round(min(100.0, max(0.0, quality)), 1),
            signals=signals,
            explanation=explanation,
        )

    def apply_feedback_multipliers(
        self,
        base_score: float,
        job: Job,
        adjustments: list[ScoringAdjustment],
    ) -> float:
        """Apply feedback-derived multipliers to a base score."""
        multiplier = 1.0
        description_lower = (job.description_clean or "").lower()

        for adj in adjustments:
            if adj.signal_type == "company":
                if adj.signal_value.lower() == job.company.lower():
                    multiplier *= adj.multiplier
            elif adj.signal_type == "domain":
                if adj.signal_value.lower() in description_lower:
                    multiplier *= adj.multiplier
            elif adj.signal_type == "title_keyword":
                if adj.signal_value.lower() in job.title.lower():
                    multiplier *= adj.multiplier

        return round(min(100.0, max(0.0, base_score * multiplier)), 1)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _score_relevance(self, job: Job) -> tuple[float, dict[str, float]]:
        signals: dict[str, float] = {}
        w = self.config.relevance_weights
        title_lower = job.title.lower()
        desc_lower = (job.description_clean or "").lower()
        full_text = f"{title_lower} {desc_lower}"

        # --- Title match ---
        title_matched = False
        for pt in self.priority_terms:
            if pt in title_lower:
                signals["title_exact_match"] = w.get("title_exact_match", 30)
                title_matched = True
                break

        if not title_matched:
            for bucket in self.config.domain_buckets.values():
                if any(kw.lower() in title_lower for kw in bucket.keywords):
                    signals["title_partial_match"] = w.get("title_partial_match", 15)
                    break

        # --- Seniority ---
        for kw in self.config.seniority_keywords:
            if kw.lower() in title_lower:
                signals["seniority_match"] = w.get("seniority_match", 20)
                break

        # --- Domain fit (pick the highest-scoring bucket) ---
        best_domain_score = 0.0
        for bucket_name, bucket in self.config.domain_buckets.items():
            hits = sum(1 for kw in bucket.keywords if kw.lower() in full_text)
            bucket_score = min(w.get("domain_fit", 15), hits * 3) * bucket.weight
            if bucket_score > best_domain_score:
                best_domain_score = bucket_score
        if best_domain_score > 0:
            signals["domain_fit"] = best_domain_score

        # --- Keyword density (count all domain keywords in description) ---
        all_keywords = [kw for b in self.config.domain_buckets.values() for kw in b.keywords]
        matched_kws = list({kw for kw in all_keywords if kw.lower() in desc_lower})
        job.keywords_matched = matched_kws  # side-effect: annotate the job
        density = min(w.get("keyword_density", 25), len(matched_kws) * 2)
        if density > 0:
            signals["keyword_density"] = density

        # --- Negative signals ---
        neg_hits = sum(1 for neg in self.config.negative_keywords if neg.lower() in full_text)
        if neg_hits > 0:
            neg_score = max(
                w.get("negative_signal_cap", -15),
                neg_hits * w.get("negative_signal_per_hit", -5),
            )
            signals["negative_signals"] = neg_score

        total = sum(signals.values())
        return total, signals

    def _score_quality(self, job: Job) -> float:
        qw = self.config.quality_weights
        score = 0.0

        # Salary presence
        if job.salary_min is not None or job.salary_max is not None:
            score += qw.get("salary_present", 20)

        # Description length
        word_count = len((job.description_clean or "").split())
        if word_count >= 400:
            score += qw.get("description_length_full", 20)
        elif word_count >= 150:
            score += qw.get("description_length_partial", 10)

        # Direct ATS link (URL contains known ATS domains)
        ats_domains = (
            "greenhouse.io", "lever.co", "workday.com", "icims.com",
            "myworkdayjobs.com", "smartrecruiters.com", "ashbyhq.com",
        )
        url = (job.source_url or "").lower()
        if any(d in url for d in ats_domains):
            score += qw.get("direct_ats_link", 15)

        # Fresh posting (days since posted)
        from datetime import date
        if job.posted_date:
            days_old = (date.today() - job.posted_date).days
            if days_old <= 14:
                score += qw.get("fresh_posting_14d", 15)
            elif days_old <= 30:
                score += qw.get("fresh_posting_30d", 8)

        # Low duplicate risk
        if not job.possible_cross_site_duplicate:
            score += qw.get("low_duplicate_risk", 15)

        return score

    def _explain(self, signals: dict[str, float]) -> str:
        """Return top-3 signals as human-readable explanation."""
        top = sorted(signals.items(), key=lambda x: abs(x[1]), reverse=True)[:3]
        parts = []
        for name, pts in top:
            label = name.replace("_", " ").title()
            parts.append(f"{label}: {pts:+.0f}pts")
        return "; ".join(parts) if parts else "No signals matched"
