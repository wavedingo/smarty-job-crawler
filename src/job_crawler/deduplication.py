"""Deduplication: exact and fuzzy duplicate detection for Job objects."""

import hashlib
import re

from rapidfuzz import fuzz

from job_crawler.models import Job


def _normalize_text(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace for comparison."""
    text = text.lower()
    text = re.sub(r'[^\w\s]', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()


def make_job_id(source_site: str, external_id: str | None, url: str) -> str:
    """Generate a stable job_id. Same algorithm as normalizer — kept here as a utility."""
    key = f"{source_site}:{external_id or url}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def make_compound_key(company: str, title: str, location: str | None) -> str:
    """Hash of normalized company+title+location for exact duplicate detection."""
    text = (
        f"{_normalize_text(company)}"
        f"|{_normalize_text(title)}"
        f"|{_normalize_text(location or '')}"
    )
    return hashlib.sha256(text.encode()).hexdigest()[:16]


class DuplicateDetector:
    FUZZY_TITLE_THRESHOLD = 85   # token_sort_ratio score 0–100
    COMPANY_THRESHOLD = 85

    def find_fuzzy_duplicates(
        self,
        new_jobs: list[Job],
        existing_jobs: list[Job],
    ) -> list[tuple[Job, Job, float]]:
        """
        For each new job, check against existing_jobs for fuzzy matches.

        Returns list of (new_job, existing_job, similarity_score) for likely
        duplicates.  A match requires both title similarity >
        FUZZY_TITLE_THRESHOLD AND company similarity > COMPANY_THRESHOLD.
        """
        matches: list[tuple[Job, Job, float]] = []
        for new_job in new_jobs:
            for existing in existing_jobs:
                if new_job.job_id == existing.job_id:
                    continue

                company_score = fuzz.token_sort_ratio(
                    _normalize_text(new_job.company),
                    _normalize_text(existing.company),
                )
                if company_score < self.COMPANY_THRESHOLD:
                    continue

                title_score = fuzz.token_sort_ratio(
                    _normalize_text(new_job.title),
                    _normalize_text(existing.title),
                )
                if title_score >= self.FUZZY_TITLE_THRESHOLD:
                    similarity = (title_score + company_score) / 2
                    matches.append((new_job, existing, similarity))

        return matches

    def group_cross_site_duplicates(
        self,
        matches: list[tuple[Job, Job, float]],
    ) -> dict[str, int]:
        """
        From fuzzy matches, assign duplicate_group_id values.

        Returns {job_id: group_id} for jobs that should be grouped.
        Uses a simple union-find (DFS over adjacency list) approach.
        """
        adjacency: dict[str, set[str]] = {}
        for new_job, existing, _ in matches:
            adjacency.setdefault(new_job.job_id, set()).add(existing.job_id)
            adjacency.setdefault(existing.job_id, set()).add(new_job.job_id)

        visited: set[str] = set()
        groups: list[set[str]] = []

        for job_id in adjacency:
            if job_id not in visited:
                group: set[str] = set()
                stack = [job_id]
                while stack:
                    curr = stack.pop()
                    if curr in visited:
                        continue
                    visited.add(curr)
                    group.add(curr)
                    stack.extend(adjacency.get(curr, set()) - visited)
                if len(group) > 1:
                    groups.append(group)

        result: dict[str, int] = {}
        for group_num, group in enumerate(groups, start=1):
            for job_id in group:
                result[job_id] = group_num

        return result
