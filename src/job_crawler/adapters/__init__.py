"""Adapters package — source-specific scrapers and API clients."""

from .base import BaseAdapter
from .indeed import IndeedAdapter
from .greenhouse import GreenhouseAdapter
from .lever import LeverAdapter
from .dice import DiceAdapter
from .ashby import AshbyAdapter
from .perplexity import PerplexityAdapter
from .playwright_openai import OpenAIPlaywrightAdapter
from .wttj import WelcomeToTheJungleAdapter
from .google_careers import GoogleCareersAdapter

# Registry: adapter name → class
ADAPTER_REGISTRY: dict[str, type[BaseAdapter]] = {
    "indeed": IndeedAdapter,
    "greenhouse": GreenhouseAdapter,
    "lever": LeverAdapter,
    "dice": DiceAdapter,
    "ashby": AshbyAdapter,
    "perplexity": PerplexityAdapter,
    "playwright_openai": OpenAIPlaywrightAdapter,
    "wttj": WelcomeToTheJungleAdapter,
    "google_careers": GoogleCareersAdapter,
}


def get_adapter(name: str) -> BaseAdapter:
    """Instantiate an adapter by name. Raises KeyError if unknown."""
    cls = ADAPTER_REGISTRY[name]
    return cls()
