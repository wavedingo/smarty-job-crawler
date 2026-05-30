import httpx
from job_crawler.models import RawJob
from .base import BaseAdapter


class WelcomeToTheJungleAdapter(BaseAdapter):
    name = "wttj"

    @property
    def tier(self) -> int:
        return 2

    async def fetch(self, term: str, config: dict, client: httpx.AsyncClient) -> list[RawJob]:
        try:
            response = await client.get(
                "https://api.welcometothejungle.com/api/v1/jobs/search",
                params={"query": term, "page": 1},
                headers={"Accept": "application/json", "Accept-Language": "en"},
            )
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            print(f"[wttj] Unavailable for '{term}': {e}")
            return []

        results = []
        for job in data.get("jobs", []) or data.get("data", []) or []:
            try:
                results.append(RawJob(
                    source_site="wttj",
                    external_id=str(job.get("id", job.get("slug", ""))),
                    url=job.get("canonical_url", "") or job.get("url", ""),
                    title=job.get("name", "") or job.get("title", ""),
                    company=(
                        job.get("organization", {}).get("name", "")
                        or job.get("company", {}).get("name", "")
                    ),
                    search_term=term,
                    raw_data=job,
                ))
            except Exception:
                continue  # skip malformed entries

        return results
