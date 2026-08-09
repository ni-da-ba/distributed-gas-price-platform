from __future__ import annotations

from gas_price_platform.analytics import analyze_region
from gas_price_platform.api import create_app
from gas_price_platform.datasource import DataSourceError
from gas_price_platform.models import AnalysisRequest, JobStatus, utc_now


class FixtureSource:
    def __init__(self, observations) -> None:
        self.observations = observations

    def fetch_all(self):
        return self.observations


class FailingSource:
    def fetch_all(self):
        raise DataSourceError("fixture upstream failed")


def test_health_and_regions(memory_store) -> None:
    client = create_app(store=memory_store).test_client()

    assert client.get("/health/live").get_json() == {"status": "live"}
    assert client.get("/health/ready").get_json() == {"status": "ready"}
    assert client.get("/v1/regions").get_json() == {"regions": ["albany", "new-york-state"]}


def test_prices_filter_by_date(memory_store) -> None:
    client = create_app(store=memory_store).test_client()

    response = client.get("/v1/prices?region=albany&start=2024-01-08&end=2024-01-15")

    assert response.status_code == 200
    assert response.get_json()["observations"] == [
        {"date": "2024-01-08", "usd_per_gallon": 3.1},
        {"date": "2024-01-15", "usd_per_gallon": 3.2},
    ]


def test_prices_validate_parameters(memory_store) -> None:
    client = create_app(store=memory_store).test_client()

    missing = client.get("/v1/prices")
    invalid = client.get("/v1/prices?region=albany&start=01-08-2024")

    assert missing.status_code == 400
    assert missing.get_json()["error"]["code"] == "invalid_region"
    assert invalid.status_code == 400
    assert invalid.get_json()["error"]["code"] == "invalid_date"


def test_create_and_inspect_job(memory_store) -> None:
    client = create_app(store=memory_store).test_client()

    created = client.post(
        "/v1/jobs/region-analysis",
        json={"region": "albany", "start": "2024-01-01", "end": "2024-01-15"},
    )

    assert created.status_code == 202
    job = created.get_json()
    assert job["status"] == "submitted"
    assert client.get(f"/v1/jobs/{job['id']}").status_code == 200
    assert client.get(f"/v1/jobs/{job['id']}/result").status_code == 409


def test_refresh_replaces_data(memory_store, observations) -> None:
    client = create_app(
        store=memory_store, data_source=FixtureSource(observations[:1])
    ).test_client()

    response = client.post("/v1/data/refresh")

    assert response.get_json() == {"observations_stored": 1}
    assert len(memory_store.list_observations()) == 1


def test_unknown_series_and_job_are_404(memory_store) -> None:
    client = create_app(store=memory_store).test_client()

    assert client.get("/v1/prices?region=missing").status_code == 404
    assert client.get("/v1/jobs/missing").status_code == 404


def test_summary_and_job_listing(memory_store) -> None:
    client = create_app(store=memory_store).test_client()
    created = client.post("/v1/jobs/region-analysis", json={"region": "albany"}).get_json()

    summary = client.get("/v1/summary?region=albany")
    jobs = client.get("/v1/jobs")

    assert summary.status_code == 200
    assert summary.get_json()["summary"]["count"] == 3
    assert jobs.get_json()["jobs"][0]["id"] == created["id"]


def test_completed_job_result(memory_store) -> None:
    job = memory_store.enqueue_analysis(AnalysisRequest(region="albany"))
    job.status = JobStatus.COMPLETE
    job.result = analyze_region(memory_store.list_observations(), "albany")
    job.updated_at = utc_now()
    memory_store.save_job(job)
    client = create_app(store=memory_store).test_client()

    response = client.get(f"/v1/jobs/{job.id}/result")

    assert response.status_code == 200
    assert response.get_json()["result"]["region"] == "albany"


def test_job_request_validation(memory_store) -> None:
    client = create_app(store=memory_store).test_client()

    assert client.post("/v1/jobs/region-analysis", data="not-json").status_code == 400
    assert client.post("/v1/jobs/region-analysis", json={}).status_code == 400
    invalid_interval = client.post(
        "/v1/jobs/region-analysis",
        json={"region": "albany", "start": "2024-02-01", "end": "2024-01-01"},
    )
    assert invalid_interval.status_code == 400
    assert invalid_interval.get_json()["error"]["code"] == "invalid_interval"


def test_query_interval_and_upstream_failure_validation(memory_store) -> None:
    client = create_app(store=memory_store, data_source=FailingSource()).test_client()

    reversed_interval = client.get("/v1/prices?region=albany&start=2024-02-01&end=2024-01-01")
    refresh = client.post("/v1/data/refresh")

    assert reversed_interval.status_code == 400
    assert reversed_interval.get_json()["error"]["code"] == "invalid_interval"
    assert refresh.status_code == 502
    assert refresh.get_json()["error"]["code"] == "upstream_unavailable"
