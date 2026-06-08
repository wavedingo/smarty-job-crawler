import logging
import httpx
from job_crawler.models import RawJob
from .base import BaseAdapter

logger = logging.getLogger(__name__)


class AshbyAdapter(BaseAdapter):
    """Tier 1 adapter for Ashby ATS public job boards.

    Ashby is used by OpenAI, Perplexity, Notion, and many other companies.
    Public API requires no authentication.
    """

    name = "ashby"

    def __init__(self):
        self._cache: dict[str, list[RawJob]] = {}

    async def fetch(self, term: str, config: dict, client: httpx.AsyncClient) -> list[RawJob]:
        return []

    async def fetch_all(self, terms: list[str], config: dict) -> list[RawJob]:
        org_id = config.get("org_id", "")
        if not org_id:
            logger.warning("[ashby] No org_id configured")
            return []

        if org_id in self._cache:
            return self._cache[org_id]

        url = f"https://api.ashbyhq.com/posting-api/job-board/{org_id}"

        try:
            async with httpx.AsyncClient(
                timeout=30.0,
                headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
                    "Accept": "application/json",
                },
                follow_redirects=True,
            ) as client:
                response = await client.get(url)
                response.raise_for_status()
                data = response.json()
        except Exception as e:
            logger.warning("[ashby:%s] Error: %s", org_id, e)
            return []

        results = []
        for posting in data.get("jobPostings", []):
            if not posting.get("isListed", True):
                continue
            results.append(RawJob(
                source_site=f"ashby:{org_id}",
                external_id=posting.get("id", ""),
                url=posting.get("applyUrl", "") or posting.get("externalLink", ""),
                title=posting.get("title", ""),
                company=org_id.capitalize(),
                search_term=None,
                raw_data={
                    "location": posting.get("locationName", ""),
                    "department": posting.get("departmentName", ""),
                    "published_date": posting.get("publishedDate", ""),
                    "description_html": posting.get("descriptionHtml", ""),
                    "employment_type": posting.get("employmentType", ""),
                    "compensation": posting.get("compensation", {}),
                },
            ))

        logger.info("[ashby:%s] fetched %d postings", org_id, len(results))
        self._cache[org_id] = results
        return results

    def reset_cache(self) -> None:
        self._cache.clear()
