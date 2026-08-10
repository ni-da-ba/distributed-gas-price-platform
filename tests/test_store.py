from __future__ import annotations

from datetime import date

import fakeredis

from gas_price_platform.models import AnalysisRequest
from gas_price_platform.store import RedisStore


def test_redis_store_round_trip(observations) -> None:
    store = RedisStore(fakeredis.FakeRedis(decode_responses=True), queue_name="test-queue")

    assert store.replace_observations(observations) == 3
    assert [item.date for item in store.list_observations(date(2024, 1, 8))] == [
        date(2024, 1, 8),
        date(2024, 1, 15),
    ]


def test_redis_store_queues_and_persists_job() -> None:
    store = RedisStore(fakeredis.FakeRedis(decode_responses=True), queue_name="test-queue")

    job = store.enqueue_analysis(AnalysisRequest(region="albany"))

    assert store.claim_job() == job.id
    assert store.get_job(job.id).request.region == "albany"
    assert [saved.id for saved in store.list_jobs()] == [job.id]
