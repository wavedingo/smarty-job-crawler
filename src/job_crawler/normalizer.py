"""Normalizer: converts RawJob → Job."""

import hashlib
import logging
import re
from datetime import date, datetime, timezone

from bs4 import BeautifulSoup

from job_crawler.models import Job, RawJob, RemoteStatus

REMOTE_KEYWORDS = {"remote", "work from home", "wfh", "fully remote", "100% remote"}
HYBRID_KEYWORDS = {"hybrid", "partially remote", "flexible location"}
ONSITE_KEYWORDS = {"on-site", "onsite", "in-office", "in office", "on site"}

SENIORITY_PATTERNS = [
    (r'\b(C[XS]O|Chief [A-Z][\w]+ Officer|CEO|COO|CRO|CMO)\b', 'C-Suite'),
    (r'\b(SVP|Senior Vice President|EVP|Executive Vice President)\b', 'SVP/EVP'),
    (r'\b(VP|Vice President)\b', 'VP'),
    (r'\b(Director|Dir\.)\b', 'Director'),
    (r'\b(General Manager|GM)\b', 'General Manager'),
    (r'\b(Head of|Head,)\b', 'Head of'),
    (r'\b(Senior Manager|Sr\. Manager)\b', 'Senior Manager'),
    (r'\b(Manager)\b', 'Manager'),
]


class Normalizer:
    def __init__(self, config=None):
        self.config = config

    def normalize(self, raw: RawJob) -> Job | None:
        """Convert a RawJob to a Job. Return None if the job lacks required fields."""
        title = (raw.title or "").strip()
        company = (raw.company or "").strip()
        url = (raw.url or "").strip()

        if not title or not company or not url:
            return None

        # Generate stable job_id
        key = f"{raw.source_site}:{raw.external_id or url}"
        job_id = hashlib.sha256(key.encode()).hexdigest()[:16]

        now = datetime.now(timezone.utc)

        # Extract description
        description_raw = self._get_description(raw)
        description_clean = self._strip_html(description_raw) if description_raw else None

        text_for_analysis = f"{title} {description_clean or ''}".lower()

        return Job(
            job_id=job_id,
            source_site=raw.source_site,
            source_url=url,
            canonical_url=url,
            title=title,
            company=company,
            location=self._get_location(raw),
            remote_status=self._detect_remote(raw, text_for_analysis),
            posted_date=self._parse_posted_date(raw),
            discovered_date=date.today(),
            salary_min=None,  # filled later in normalize_many
            salary_max=None,
            seniority_level=self._detect_seniority(title),
            employment_type=self._detect_employment_type(text_for_analysis),
            description_raw=description_raw,
            description_clean=description_clean,
            required_skills=self._extract_required_skills(description_clean or ""),
            preferred_skills=self._extract_preferred_skills(description_clean or ""),
            created_at=now,
            updated_at=now,
        )

    def normalize_many(self, raws: list[RawJob]) -> list[tuple[Job, str | None]]:
        """Normalize a list of RawJobs. Returns list of (Job, search_term) pairs, skipping failures."""
        results = []
        for raw in raws:
            try:
                job = self.normalize(raw)
                if job is not None:
                    text = f"{raw.raw_data.get('salary_text', '')} {raw.raw_data.get('salary', '')} {job.description_clean or ''}"
                    sal_min, sal_max = self._extract_salary(text)
                    job.salary_min = sal_min
                    job.salary_max = sal_max
                    results.append((job, raw.search_term))
            except Exception as e:
                logging.getLogger(__name__).warning("Normalization failed for %s: %s", raw.url, e)
        return results

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_description(self, raw: RawJob) -> str | None:
        """Extract the best available description from raw_data."""
        d = raw.raw_data
        return (
            d.get("content")                    # Greenhouse HTML
            or d.get("description_plain")       # Lever plain text
            or d.get("summary")                 # Indeed HTML summary
            or d.get("description_fragment")    # Dice snippet
            or d.get("description", "")
            or None
        )

    def _get_location(self, raw: RawJob) -> str | None:
        d = raw.raw_data
        return d.get("location") or d.get("location_name") or None

    def _strip_html(self, html: str) -> str:
        """Strip HTML tags and clean up whitespace."""
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text(separator=" ")
        return re.sub(r'\s+', ' ', text).strip()

    def _extract_salary(self, text: str) -> tuple[float | None, float | None]:
        """Extract salary min/max from text. Handles K notation and hourly conversion."""
        # Match patterns like: $150K, $150k, $150,000, $150K-$200K, $150,000-$200,000
        pattern = re.compile(
            r'\$\s*([\d,]+(?:\.\d+)?)\s*([Kk])?\s*(?:[-–]\s*\$?\s*([\d,]+(?:\.\d+)?)\s*([Kk]?))?',
            re.IGNORECASE
        )
        for match in pattern.finditer(text):
            low_str, low_k, high_str, high_k = match.groups()

            try:
                low = float(low_str.replace(",", ""))
                if low_k:
                    low *= 1000
                elif low < 500:
                    low *= 2080  # Assume hourly, convert to annual

                high = None
                if high_str:
                    high = float(high_str.replace(",", ""))
                    if high_k:
                        high *= 1000
                    elif high < 500:
                        high *= 2080  # Hourly to annual for high end too

                # Sanity check: must look like annual salary
                if low >= 20000:
                    return low, high
            except (ValueError, TypeError):
                continue

        return None, None

    def _detect_remote(self, raw: RawJob, text: str) -> RemoteStatus:
        """Detect remote status from location + description."""
        location = (self._get_location(raw) or "").lower()

        if any(kw in location for kw in REMOTE_KEYWORDS):
            return RemoteStatus.REMOTE
        if any(kw in location for kw in HYBRID_KEYWORDS):
            return RemoteStatus.HYBRID
        if any(kw in location for kw in ONSITE_KEYWORDS):
            return RemoteStatus.ONSITE

        if any(kw in text for kw in REMOTE_KEYWORDS):
            return RemoteStatus.REMOTE
        if any(kw in text for kw in HYBRID_KEYWORDS):
            return RemoteStatus.HYBRID

        return RemoteStatus.UNKNOWN

    def _detect_seniority(self, title: str) -> str | None:
        """Extract seniority level from job title."""
        for pattern, level in SENIORITY_PATTERNS:
            if re.search(pattern, title, re.IGNORECASE):
                return level
        return None

    def _detect_employment_type(self, text: str) -> str | None:
        """Detect employment type from text."""
        if re.search(r'\b(full[- ]time|permanent)\b', text, re.IGNORECASE):
            return "full-time"
        if re.search(r'\b(part[- ]time)\b', text, re.IGNORECASE):
            return "part-time"
        if re.search(r'\b(contract|contractor|freelance|1099)\b', text, re.IGNORECASE):
            return "contract"
        if re.search(r'\b(intern|internship)\b', text, re.IGNORECASE):
            return "internship"
        return None

    def _extract_required_skills(self, text: str) -> list[str]:
        """Extract required skills from descriptions with 'Requirements' sections."""
        return self._extract_skills_section(
            text, r'requirements?|qualifications?|must have|you will need'
        )

    def _extract_preferred_skills(self, text: str) -> list[str]:
        """Extract preferred skills from descriptions with 'Nice to have' sections."""
        return self._extract_skills_section(
            text, r'preferred|nice[- ]to[- ]have|bonus|plus|desired'
        )

    def _extract_skills_section(self, text: str, section_pattern: str) -> list[str]:
        """Find a section header and extract bullet-point items from it."""
        match = re.search(section_pattern, text, re.IGNORECASE)
        if not match:
            return []
        section = text[match.start():match.start() + 500]
        bullets = re.findall(r'[•\-\*]\s*([^\n•\-\*]{10,100})', section)
        return [b.strip() for b in bullets[:10]]

    def _parse_posted_date(self, raw: RawJob) -> date | None:
        """Parse posted date from raw_data."""
        d = raw.raw_data
        date_str = (
            d.get("published")
            or d.get("posted_date")
            or d.get("updated_at")
            or d.get("date_posted")
            or d.get("created_at")
        )
        if not date_str:
            return None
        try:
            from dateutil.parser import parse as dateutil_parse
            return dateutil_parse(str(date_str)).date()
        except Exception:
            return None
