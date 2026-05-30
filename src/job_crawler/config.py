"""YAML config loader — reads sources.yaml, search_terms.yaml, scoring.yaml."""

from dataclasses import dataclass, field
from pathlib import Path

import yaml


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class SourceConfig:
    name: str
    adapter: str
    enabled: bool
    config: dict  # adapter-specific config (raw dict, adapters handle it)


@dataclass
class DomainBucket:
    weight: float
    keywords: list[str]


@dataclass
class ScoringConfig:
    relevance_weights: dict[str, float]
    seniority_keywords: list[str]
    domain_buckets: dict[str, DomainBucket]
    negative_keywords: list[str]
    quality_weights: dict[str, float]
    location_neutral: bool
    preferred_remote_statuses: list[str]


@dataclass
class AppConfig:
    sources: dict[str, SourceConfig]
    scoring: ScoringConfig
    priority_terms: list[str]
    boolean_searches: list[dict]       # list of {"query": str, "enabled": bool}
    categories: dict[str, dict]        # category_name → {"enabled": bool, "terms": list[str]}
    max_terms_per_run: int = 20        # from sources.yaml global config


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

def _find_config_dir() -> Path:
    """Return <project_root>/config — two levels up from src/job_crawler/."""
    # This file lives at src/job_crawler/config.py
    return Path(__file__).parent.parent.parent / "config"


def _load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _parse_sources(data: dict) -> tuple[dict[str, SourceConfig], int]:
    """Parse sources.yaml data. Returns (sources_dict, max_terms_per_run)."""
    global_cfg = data.get("global", {})
    max_terms_per_run = int(global_cfg.get("max_terms_per_run", 20))

    sources: dict[str, SourceConfig] = {}
    for name, raw in data.get("sources", {}).items():
        sources[name] = SourceConfig(
            name=name,
            adapter=raw.get("adapter", name),
            enabled=bool(raw.get("enabled", True)),
            config=raw.get("config", {}),
        )
    return sources, max_terms_per_run


def _parse_scoring(data: dict) -> ScoringConfig:
    """Parse scoring.yaml data."""
    domain_buckets: dict[str, DomainBucket] = {}
    for bucket_name, bucket_data in data.get("domain_buckets", {}).items():
        domain_buckets[bucket_name] = DomainBucket(
            weight=float(bucket_data.get("weight", 1.0)),
            keywords=list(bucket_data.get("keywords", [])),
        )

    location_cfg = data.get("location", {})
    return ScoringConfig(
        relevance_weights={k: float(v) for k, v in data.get("relevance_weights", {}).items()},
        seniority_keywords=list(data.get("seniority_keywords", [])),
        domain_buckets=domain_buckets,
        negative_keywords=list(data.get("negative_keywords", [])),
        quality_weights={k: float(v) for k, v in data.get("quality_weights", {}).items()},
        location_neutral=bool(location_cfg.get("neutral", True)),
        preferred_remote_statuses=list(location_cfg.get("preferred_remote_statuses", [])),
    )


def _parse_search_terms(data: dict) -> tuple[list[str], list[dict], dict[str, dict]]:
    """Parse search_terms.yaml. Returns (priority_terms, boolean_searches, categories)."""
    priority_terms = list(data.get("priority_terms", []))
    boolean_searches = list(data.get("boolean_searches", []))
    categories = {
        name: {"enabled": cat.get("enabled", True), "terms": list(cat.get("terms", []))}
        for name, cat in data.get("categories", {}).items()
    }
    return priority_terms, boolean_searches, categories


def load_config(config_dir: Path | None = None) -> AppConfig:
    """Load all three YAML files and return AppConfig."""
    if config_dir is None:
        config_dir = _find_config_dir()

    sources_data = _load_yaml(config_dir / "sources.yaml")
    scoring_data = _load_yaml(config_dir / "scoring.yaml")
    terms_data = _load_yaml(config_dir / "search_terms.yaml")

    sources, max_terms_per_run = _parse_sources(sources_data)
    scoring = _parse_scoring(scoring_data)
    priority_terms, boolean_searches, categories = _parse_search_terms(terms_data)

    return AppConfig(
        sources=sources,
        scoring=scoring,
        priority_terms=priority_terms,
        boolean_searches=boolean_searches,
        categories=categories,
        max_terms_per_run=max_terms_per_run,
    )
