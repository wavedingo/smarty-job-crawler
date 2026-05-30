import httpx
from job_crawler.models import RawJob
from .base import BaseAdapter


class DiceAdapter(BaseAdapter):
    name = "dice"

    async def fetch(self, term: str, config: dict, client: httpx.AsyncClient) -> list[RawJob]:
        page_size = config.get("results_per_query", 20)
        params = {
            "q": term,
            "pageSize": page_size,
            "pageNumber": 1,
            "countryCode2": "US",
        }

        try:
            response = await client.get(
                "https://job-search-api.svc.dhigroupinc.com/v1/dice/jobs/search",
                params=params,
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            print(f"[dice] Error for '{term}': {e}")
            return []

        results = []
        for hit in data.get("data", {}).get("hits", []):
            results.append(RawJob(
                source_site="dice",
                external_id=hit.get("id", ""),
                url=hit.get("applyUrl", "") or hit.get("jobDetailUrl", ""),
                title=hit.get("jobTitle", ""),
                company=hit.get("companyName", ""),
                search_term=term,
                raw_data={
                    "location": hit.get("location", ""),
                    "posted_date": hit.get("postedDate", ""),
                    "remote_work_type": hit.get("remoteWorkType", ""),
                    "salary": hit.get("salary", ""),
                    "employment_type": hit.get("employmentType", ""),
                    "description_fragment": hit.get("descriptionFragment", ""),
                    "skills": hit.get("skills", []),
                },
            ))

        return results
