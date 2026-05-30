from abc import ABC, abstractmethod
from typing import ClassVar
import asyncio
import logging
import httpx
from job_crawler.models import RawJob

logger = logging.getLogger(__name__)


class BaseAdapter(ABC):
    name: ClassVar[str]  # matches the adapter key in sources.yaml

    @abstractmethod
    async def fetch(
        self,
        term: str,
        config: dict,
        client: httpx.AsyncClient,
    ) -> list[RawJob]:
        """
        Fetch raw jobs for a search term.

        ATS-style adapters (Greenhouse, Lever) should fetch all postings once
        and cache per run; keyword filtering happens in the normalizer.
        For search-based adapters (Indeed, Dice), run a search query per term.

        Must return an empty list (not raise) if the source is unavailable.
        """
        ...

    @property
    def supports_boolean(self) -> bool:
        """True if the source supports Boolean query syntax."""
        return False

    @property
    def tier(self) -> int:
        """1 = reliable, 2 = best-effort (may fail silently)."""
        return 1

    async def fetch_all(
        self,
        terms: list[str],
        config: dict,
    ) -> list[RawJob]:
        """
        Default implementation: iterate terms sequentially with delay.
        ATS adapters should override this to fetch all postings once and cache.
        """
        results: list[RawJob] = []
        async with httpx.AsyncClient(
            timeout=30.0,
            headers={"User-Agent": "Mozilla/5.0 (compatible; job-crawler/1.0)"},
            follow_redirects=True,
        ) as client:
            for term in terms:
                try:
                    results.extend(await self.fetch(term, config, client))
                except Exception as e:
                    # Log but continue
                    log = logger.warning if self.tier == 1 else logger.debug
                    log("[%s] Error fetching '%s': %s", self.name, term, e)
                delay = config.get("delay_seconds", 1.0)
                if delay > 0:
                    await asyncio.sleep(delay)
        return results
