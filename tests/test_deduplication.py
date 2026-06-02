import pytest
from datetime import date, datetime, timezone
from job_crawler.deduplication import DuplicateDetector, make_compound_key
from job_crawler.models import Job, RemoteStatus

def make_job(job_id, title, company, location=None):
    now = datetime.now(timezone.utc)
    return Job(
        job_id=job_id,
        source_site="test",
        source_url=f"https://example.com/{job_id}",
        title=title,
        company=company,
        location=location,
        discovered_date=date.today(),
        created_at=now,
        updated_at=now,
    )

def test_compound_key_is_deterministic():
    k1 = make_compound_key("Acme Corp", "VP eCommerce", "New York")
    k2 = make_compound_key("Acme Corp", "VP eCommerce", "New York")
    assert k1 == k2

def test_compound_key_differs_by_company():
    k1 = make_compound_key("Acme Corp", "VP eCommerce", "New York")
    k2 = make_compound_key("Other Corp", "VP eCommerce", "New York")
    assert k1 != k2

def test_compound_key_normalizes_case():
    k1 = make_compound_key("ACME CORP", "VP ECOMMERCE", "NEW YORK")
    k2 = make_compound_key("acme corp", "vp ecommerce", "new york")
    assert k1 == k2

def test_fuzzy_match_above_threshold():
    detector = DuplicateDetector()
    j1 = make_job("j1", "VP of eCommerce", "Acme Corp")
    j2 = make_job("j2", "VP, eCommerce", "Acme Corp")  # Same role, slightly different title

    matches = detector.find_fuzzy_duplicates([j1], [j2])
    assert len(matches) == 1
    _, _, score = matches[0]
    assert score > 85

def test_fuzzy_no_match_different_company():
    detector = DuplicateDetector()
    j1 = make_job("j1", "VP eCommerce", "Acme Corp")
    j2 = make_job("j2", "VP eCommerce", "Totally Different Company Inc")

    matches = detector.find_fuzzy_duplicates([j1], [j2])
    assert len(matches) == 0

def test_fuzzy_no_match_different_title():
    detector = DuplicateDetector()
    j1 = make_job("j1", "VP eCommerce", "Acme Corp")
    j2 = make_job("j2", "Junior Coordinator Marketing", "Acme Corp")

    matches = detector.find_fuzzy_duplicates([j1], [j2])
    assert len(matches) == 0

def test_same_job_id_not_matched():
    """A job should not be matched as a duplicate of itself."""
    detector = DuplicateDetector()
    j1 = make_job("same_id", "VP eCommerce", "Acme Corp")
    j2 = make_job("same_id", "VP eCommerce", "Acme Corp")

    matches = detector.find_fuzzy_duplicates([j1], [j2])
    assert len(matches) == 0

def test_group_cross_site_duplicates():
    detector = DuplicateDetector()
    j1 = make_job("j1", "VP eCommerce", "Acme")
    j2 = make_job("j2", "VP of eCommerce", "Acme")
    j3 = make_job("j3", "Senior Director Sales", "Other")

    matches = [(j1, j2, 91.0)]
    groups = detector.group_cross_site_duplicates(matches)

    assert "j1" in groups
    assert "j2" in groups
    assert groups["j1"] == groups["j2"]  # Same group
    assert "j3" not in groups  # No match for j3
