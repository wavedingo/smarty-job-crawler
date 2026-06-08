import logging
import re
from job_crawler.models import RawJob
from .base import BaseAdapter

logger = logging.getLogger(__name__)

_CAREERS_URL = "https://openai.com/careers/search/"
# Matches /careers/{slug}/ paths (not the top-level /careers/ landing page)
_JOB_PATH_RE = re.compile(r"/careers/[a-z0-9][a-z0-9\-]+/", re.IGNORECASE)


class OpenAIPlaywrightAdapter(BaseAdapter):
    """Playwright DOM adapter for OpenAI's careers page.

    OpenAI renders 700+ jobs client-side with no accessible JSON API.
    Each job link has innerText: "{title}\\n{department}\\n{location}".
    """

    name = "playwright_openai"

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
            logger.warning("[openai] playwright not installed — run: uv run playwright install chromium")
            return []

        careers_url = config.get("careers_url", _CAREERS_URL)

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

            try:
                await page.goto(careers_url, wait_until="load", timeout=30000)
                await page.wait_for_timeout(3000)

                # Get all /careers/ links and filter in Python to avoid JS regex escaping issues
                raw_links = await page.eval_on_selector_all(
                    'a[href*="/careers/"]',
                    'els => els.map(e => ({href: e.href, text: e.innerText.trim()}))',
                )
                # Keep only individual job paths (e.g. /careers/vp-ecommerce-sf/), not the landing page
                raw_links = [l for l in raw_links if _JOB_PATH_RE.search(l["href"])]

                results: list[RawJob] = []
                seen: set[str] = set()

                for link in raw_links:
                    href: str = link["href"]
                    if href in seen:
                        continue
                    seen.add(href)

                    parts = [p.strip() for p in link["text"].split("\n") if p.strip()]
                    if not parts:
                        continue

                    title = parts[0]
                    department = parts[1] if len(parts) > 1 else ""
                    location = parts[2] if len(parts) > 2 else ""

                    slug = href.rstrip("/").rsplit("/", 1)[-1]

                    results.append(RawJob(
                        source_site="openai",
                        external_id=slug,
                        url=href,
                        title=title,
                        company="OpenAI",
                        search_term=None,
                        raw_data={
                            "location": location,
                            "department": department,
                        },
                    ))

                logger.info("[openai] scraped %d jobs via Playwright", len(results))
                self._cache = results
                return results

            except Exception as e:
                logger.warning("[openai] Playwright scraping failed: %s", e)
                return []
            finally:
                await browser.close()

    def reset_cache(self) -> None:
        self._cache = None
