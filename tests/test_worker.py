from __future__ import annotations

import pytest

from gas_price_platform.models import AnalysisRequest, JobStatus
from gas_price_platform.worker import process_job


def test_worker_completes_analysis(memory_store) -> None:
    job = memory_store.enqueue_analysis(AnalysisRequest(region="albany"))

    process_job(memory_store, job.id)

    completed = memory_store.get_job(job.id)
    assert completed is not None
    assert completed.status is JobStatus.COMPLETE
    assert completed.result["summary"]["count"] == 3
    assert completed.result["linear_trend"]["slope_usd_per_gallon_per_week"] == pytest.approx(0.1)


def test_worker_records_bounded_failure(memory_store) -> None:
    job = memory_store.enqueue_analysis(AnalysisRequest(region="missing"))

    process_job(memory_store, job.id)

    failed = memory_store.get_job(job.id)
    assert failed is not None
    assert failed.status is JobStatus.FAILED
    assert "no observations" in failed.error
    assert failed.result is None


def test_worker_ignores_unknown_job(memory_store, caplog) -> None:
    process_job(memory_store, "missing")

    assert "Ignoring unknown job" in caplog.text
