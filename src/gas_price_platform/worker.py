"""Asynchronous Redis queue worker."""

from __future__ import annotations

import logging
import os
import signal

from .analytics import analyze_region
from .config import Settings
from .models import JobStatus, utc_now
from .store import RedisStore, Store

LOGGER = logging.getLogger(__name__)


def process_job(store: Store, job_id: str) -> None:
    job = store.get_job(job_id)
    if job is None:
        LOGGER.warning("Ignoring unknown job %s", job_id)
        return

    job.status = JobStatus.RUNNING
    job.updated_at = utc_now()
    store.save_job(job)

    try:
        observations = store.list_observations(job.request.start, job.request.end)
        job.result = analyze_region(
            observations,
            job.request.region,
            job.request.start,
            job.request.end,
        )
        job.status = JobStatus.COMPLETE
        job.error = None
    except Exception as exc:
        LOGGER.exception("Analysis job %s failed", job_id)
        job.status = JobStatus.FAILED
        job.result = None
        job.error = str(exc)[:500]
    finally:
        job.updated_at = utc_now()
        store.save_job(job)


def run_worker(store: Store, *, poll_timeout_seconds: int = 5) -> None:
    stopping = False

    def request_stop(_signum: int, _frame: object) -> None:
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    LOGGER.info("Analysis worker started")

    while not stopping:
        job_id = store.claim_job(timeout_seconds=poll_timeout_seconds)
        if job_id:
            process_job(store, job_id)


def main() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    settings = Settings.from_env()
    store = RedisStore.from_url(settings.redis_url, queue_name=settings.queue_name)
    run_worker(store)


if __name__ == "__main__":
    main()
