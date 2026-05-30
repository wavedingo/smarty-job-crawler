import re
import feedparser
from urllib.parse import quote_plus
import httpx
from job_crawler.models import RawJob
from .base import BaseAdapter

SALARY_RE = re.compile(
    r'\$[\d,]+(?:K)?(?:\s*[-–]\s*\$[\d,]+(?:K)?)?'
    r'(?:\s*(?:a year|per year|annually|/yr|/year))?',
    re.IGNORECASE,
)


class IndeedAdapter(BaseAdapter):
    name = "indeed"

    @property
    def supports_boolean(self) -> bool:
        return True  # Indeed supports quoted phrases and basic boolean in URL

    async def fetch(self, term: str, config: dict, client: httpx.AsyncClient) -> list[RawJob]:
        limit = config.get("results_per_query", 25)
        location = config.get("location", "")
        url = (
            f"https://www.indeed.com/rss"
            f"?q={quote_plus(term)}&l={quote_plus(location)}&sort=date&limit={limit}"
        )

        try:
            response = await client.get(url)
            response.raise_for_status()
        except Exception as e:
            print(f"[indeed] HTTP error for '{term}': {e}")
            return []

        feed = feedparser.parse(response.text)
        results = []

        for entry in feed.entries:
            # Parse company from title ("Title at Company" or "Title - Company")
            raw_title = entry.get("title", "")
            company = ""
            title = raw_title

            if " - " in raw_title:
                parts = raw_title.rsplit(" - ", 1)
                title, company = parts[0].strip(), parts[1].strip()
            elif " at " in raw_title.lower():
                idx = raw_title.lower().rfind(" at ")
                title = raw_title[:idx].strip()
                company = raw_title[idx + 4:].strip()

            # Try source.title as fallback for company
            if not company and hasattr(entry, "source"):
                company = getattr(entry.source, "title", "")

            results.append(RawJob(
                source_site="indeed",
                external_id=None,
                url=entry.get("link", ""),
                title=title or raw_title,
                company=company or "Unknown",
                search_term=term,
                raw_data={
                    "summary": entry.get("summary", ""),
                    "published": entry.get("published", ""),
                    "tags": [t.term for t in getattr(entry, "tags", [])],
                    "salary_text": _extract_salary_text(entry.get("summary", "")),
                },
            ))

        return results


def _extract_salary_text(html_text: str) -> str:
    """Extract raw salary string from HTML summary if present."""
    match = SALARY_RE.search(html_text)
    return match.group(0) if match else ""
