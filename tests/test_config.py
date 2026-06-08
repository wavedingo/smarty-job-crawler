import pytest
from pathlib import Path
from job_crawler.config import load_config

def test_load_config_succeeds():
    """Config loads without error from the actual config/ directory."""
    config = load_config()
    assert config is not None
    assert len(config.sources) > 0
    assert len(config.priority_terms) == 10
    assert len(config.boolean_searches) == 6
    assert config.max_terms_per_run == 20

def test_config_has_expected_sources():
    config = load_config()
    assert "anthropic" in config.sources
    assert "openai" in config.sources
    assert "xai" in config.sources
    assert "perplexity" in config.sources
    # Confirm working sources are enabled
    assert config.sources["anthropic"].enabled is True
    assert config.sources["openai"].enabled is True

def test_scoring_config_domain_buckets():
    config = load_config()
    assert "ecommerce" in config.scoring.domain_buckets
    assert "media_podcast" in config.scoring.domain_buckets
    assert len(config.scoring.seniority_keywords) > 0

def test_config_categories_have_terms():
    config = load_config()
    assert len(config.categories) == 7
    for cat_name, cat_data in config.categories.items():
        assert "terms" in cat_data
        assert len(cat_data["terms"]) > 0, f"Category {cat_name} has no terms"
