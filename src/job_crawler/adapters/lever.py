import httpx
from datetime import datetime, timezone
from job_crawler.models import RawJob
from .base import BaseAdapter


class LeverAdapter(BaseAdapter):
    name = "lever"
    _cache: dict[str, list[RawJob]] = {}

    async def fetch(self, term: str, config: dict, client: httpx.AsyncClient) -> list[RawJob]:
        return []

    async def fetch_all(self, terms: list[str], config: dict) -> list[RawJob]:
        company_slug = config.get("company_slug", "")
        if not company_slug:
            return []

        if company_slug in self._cache:
            return self._cache[company_slug]

        url = f"https://api.lever.co/v0/postings/{company_slug}?mode=json"

        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                response = await client.get(url)
                response.raise_for_status()
                data = response.json()
        except Exception as e:
            print(f"[lever:{company_slug}] Error: {e}")
            return []

        results = []
        for posting in data:
            created_ms = posting.get("createdAt", 0)
            created_dt = (
                datetime.fromtimestamp(created_ms / 1000, tz=timezone.utc).isoformat()
                if created_ms
                else ""
            )

            results.append(RawJob(
                source_site=f"lever:{company_slug}",
                external_id=posting.get("id", ""),
                url=posting.get("hostedUrl", ""),
                title=posting.get("text", ""),
                company=company_slug.capitalize(),
                search_term=None,
                raw_data={
                    "location": posting.get("categories", {}).get("location", ""),
                    "description_plain": posting.get("descriptionPlain", ""),
                    "created_at": created_dt,
                    "team": posting.get("categories", {}).get("team", ""),
                    "commitment": posting.get("categories", {}).get("commitment", ""),
                },
            ))

        self._cache[company_slug] = results
        return results

    def reset_cache(self) -> None:
        self._cache.clear()
