import logging
from job_crawler.models import RawJob
from .base import BaseAdapter

logger = logging.getLogger(__name__)


class PerplexityAdapter(BaseAdapter):
    """Playwright adapter for Perplexity's careers page.

    Perplexity's /api/jobs endpoint requires browser cookies, so we visit the
    careers page with Playwright and intercept the JSON response the page fetches.
    """

    name = "perplexity"

    def __init__(self):
        self._cache: list[RawJob] | None = None

    async def fetch(self, term: str, config, client) -> list[RawJob]:
        return []

    async def fetch_all(self, terms: list[str], config: dict) -> list[RawJob]:
        if self._cache is not None:
            return self._cache

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.warning("[perplexity] playwright not installed — run: uv run playwright install chromium")
            return []

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            ctx = await browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 900},
            )
            page = await ctx.new_page()

            jobs_data: list[dict] = []

            async def handle_response(response):
                if "/api/jobs" in response.url and response.status == 200:
                    try:
                        data = await response.json()
                        jobs_data.extend(data.get("jobs", []))
                    except Exception:
                        pass

            page.on("response", handle_response)

            try:
                await page.goto("https://www.perplexity.ai/careers", wait_until="load", timeout=30000)
                await page.wait_for_timeout(4000)
            except Exception as e:
                logger.warning("[perplexity] page load failed: %s", e)
                await browser.close()
                return []
            finally:
                await browser.close()

        results = []
        for job in jobs_data:
            title = (job.get("title") or "").strip()
            if not title:
                continue

            location = job.get("location", "")
            secondary = job.get("secondaryLocations", [])
            if secondary:
                location = f"{location}, +{len(secondary)} more" if location else ", ".join(secondary)

            results.append(RawJob(
                source_site="perplexity",
                external_id=job.get("id", ""),
                url=job.get("jobUrl", "") or job.get("applyUrl", ""),
                title=title,
                company="Perplexity",
                search_term=None,
                raw_data={
                    "location": location,
                    "department": job.get("department", ""),
                    "team": job.get("team", ""),
                    "employment_type": job.get("employmentType", ""),
                },
            ))

        logger.info("[perplexity] fetched %d jobs via Playwright", len(results))
        self._cache = results
        return results

    def reset_cache(self) -> None:
        self._cache = None
