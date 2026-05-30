import logging
import httpx
from job_crawler.models import RawJob
from .base import BaseAdapter

logger = logging.getLogger(__name__)


class GoogleCareersAdapter(BaseAdapter):
    name = "google_careers"

    @property
    def tier(self) -> int:
        return 2

    async def fetch(self, term: str, config: dict, client: httpx.AsyncClient) -> list[RawJob]:
        try:
            response = await client.get(
                "https://careers.google.com/api/jobs/jobs-v1/search/",
                params={
                    "q": term,
                    "hl": "en_US",
                    "jlo": "en_US",
                    "li": 20,
                    "jcoid": "7940902",
                },
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            logger.warning("[google_careers] Unavailable for '%s': %s", term, e)
            return []

        results = []
        for job in data.get("jobs", []) or []:
            try:
                results.append(RawJob(
                    source_site="google_careers",
                    external_id=job.get("job_id", ""),
                    url=job.get("apply_url", "") or job.get("url", ""),
                    title=job.get("job_title", "") or job.get("title", ""),
                    company="Google",
                    search_term=term,
                    raw_data={
                        "location": job.get("location_name", ""),
                        "summary": job.get("summary", ""),
                        "date_posted": job.get("date_posted", ""),
                    },
                ))
            except Exception as e:
                logger.debug("google_careers: skipping malformed entry: %s", e)
                continue

        return results
