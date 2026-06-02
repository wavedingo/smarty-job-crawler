import pytest
from datetime import date
from job_crawler.models import RawJob, RemoteStatus
from job_crawler.normalizer import Normalizer

@pytest.fixture
def normalizer():
    return Normalizer()

def make_raw(title="VP eCommerce", company="Acme", url="https://example.com/j/1",
             source="test", external_id=None, raw_data=None):
    return RawJob(
        source_site=source,
        external_id=external_id,
        url=url,
        title=title,
        company=company,
        raw_data=raw_data or {},
    )

def test_normalize_basic(normalizer):
    raw = make_raw()
    job = normalizer.normalize(raw)
    assert job is not None
    assert job.title == "VP eCommerce"
    assert job.company == "Acme"
    assert job.source_site == "test"
    assert len(job.job_id) == 16  # sha256[:16]

def test_normalize_returns_none_for_missing_title(normalizer):
    raw = make_raw(title="")
    assert normalizer.normalize(raw) is None

def test_normalize_returns_none_for_missing_company(normalizer):
    raw = make_raw(company="")
    assert normalizer.normalize(raw) is None

def test_normalize_returns_none_for_missing_url(normalizer):
    raw = make_raw(url="")
    assert normalizer.normalize(raw) is None

def test_job_id_is_deterministic(normalizer):
    raw = make_raw(external_id="abc123")
    job1 = normalizer.normalize(raw)
    job2 = normalizer.normalize(raw)
    assert job1.job_id == job2.job_id

def test_job_id_differs_by_source(normalizer):
    raw1 = make_raw(source="indeed")
    raw2 = make_raw(source="dice")
    assert normalizer.normalize(raw1).job_id != normalizer.normalize(raw2).job_id

def test_salary_extraction_k_notation(normalizer):
    raw = make_raw(raw_data={"content": "<p>Salary: $150K - $200K per year</p>"})
    job = normalizer.normalize(raw)
    job.salary_min, job.salary_max = normalizer._extract_salary("$150K - $200K per year")
    assert job.salary_min == 150000.0
    assert job.salary_max == 200000.0

def test_salary_extraction_full_notation(normalizer):
    s_min, s_max = normalizer._extract_salary("$150,000 - $180,000 annually")
    assert s_min == 150000.0
    assert s_max == 180000.0

def test_salary_extraction_no_salary(normalizer):
    s_min, s_max = normalizer._extract_salary("No salary information available")
    assert s_min is None
    assert s_max is None

def test_remote_detection_from_location(normalizer):
    raw = make_raw(raw_data={"location": "Remote"})
    job = normalizer.normalize(raw)
    assert job.remote_status == RemoteStatus.REMOTE

def test_hybrid_detection_from_description(normalizer):
    raw = make_raw(raw_data={"content": "<p>This is a hybrid role with 2 days in office.</p>"})
    job = normalizer.normalize(raw)
    assert job.remote_status == RemoteStatus.HYBRID

def test_seniority_detection_vp(normalizer):
    raw = make_raw(title="VP of eCommerce")
    job = normalizer.normalize(raw)
    assert job.seniority_level == "VP"

def test_seniority_detection_director(normalizer):
    raw = make_raw(title="Director of Strategic Partnerships")
    job = normalizer.normalize(raw)
    assert job.seniority_level == "Director"

def test_seniority_detection_head_of(normalizer):
    raw = make_raw(title="Head of Marketplace Growth")
    job = normalizer.normalize(raw)
    assert job.seniority_level == "Head of"

def test_html_stripping(normalizer):
    raw = make_raw(raw_data={"content": "<p>We need a <strong>VP</strong> with <em>ecommerce</em> experience.</p>"})
    job = normalizer.normalize(raw)
    assert "<p>" not in (job.description_clean or "")
    assert "VP" in (job.description_clean or "")

def test_normalize_many_skips_failures(normalizer):
    raws = [
        make_raw(title="VP Sales"),  # valid
        make_raw(title=""),          # invalid — no title
        make_raw(title="Director of Partnerships"),  # valid
    ]
    results = normalizer.normalize_many(raws)
    jobs = [j for j, _ in results]
    assert len(jobs) == 2
