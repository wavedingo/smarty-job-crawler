import httpx
from job_crawler.models import RawJob
from .base import BaseAdapter


class GreenhouseAdapter(BaseAdapter):
    name = "greenhouse"
    _cache: dict[str, list[RawJob]] = {}  # board_slug → results for this run

    async def fetch(self, term: str, config: dict, client: httpx.AsyncClient) -> list[RawJob]:
        # Not used directly — all fetching in fetch_all
        return []

    async def fetch_all(self, terms: list[str], config: dict) -> list[RawJob]:
        board_slug = config.get("board_slug", "")
        if not board_slug:
            return []

        cache_key = board_slug
        if cache_key in self._cache:
            return self._cache[cache_key]

        url = f"https://boards-api.greenhouse.io/v1/boards/{board_slug}/jobs?content=true"

        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                response = await client.get(url)
                response.raise_for_status()
                data = response.json()
        except Exception as e:
            print(f"[greenhouse:{board_slug}] Error: {e}")
            return []

        results = []
        for job in data.get("jobs", []):
            results.append(RawJob(
                source_site=f"greenhouse:{board_slug}",
                external_id=str(job.get("id", "")),
                url=job.get("absolute_url", ""),
                title=job.get("title", ""),
                company=board_slug.capitalize(),
                search_term=None,  # ATS — no specific term
                raw_data={
                    "location": job.get("location", {}).get("name", ""),
                    "updated_at": job.get("updated_at", ""),
                    "content": job.get("content", ""),  # HTML description
                    "departments": job.get("departments", []),
                },
            ))

        self._cache[cache_key] = results
        return results

    def reset_cache(self) -> None:
        self._cache.clear()
