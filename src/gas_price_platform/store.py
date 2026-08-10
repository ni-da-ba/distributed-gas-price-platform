"""Redis and in-memory persistence adapters."""

from __future__ import annotations

import json
from collections import deque
from datetime import date
from threading import Lock
from typing import Protocol
from uuid import uuid4

from redis import Redis

from .models import AnalysisJob, AnalysisRequest, JobStatus, Observation, utc_now


class Store(Protocol):
    def ping(self) -> bool: ...

    def replace_observations(self, observations: list[Observation]) -> int: ...

    def list_observations(
        self, start: date | None = None, end: date | None = None
    ) -> list[Observation]: ...

    def enqueue_analysis(self, request: AnalysisRequest) -> AnalysisJob: ...

    def list_jobs(self) -> list[AnalysisJob]: ...

    def get_job(self, job_id: str) -> AnalysisJob | None: ...

    def claim_job(self, timeout_seconds: int = 0) -> str | None: ...

    def save_job(self, job: AnalysisJob) -> None: ...


class MemoryStore:
    """Deterministic store for tests and local domain validation."""

    def __init__(self) -> None:
        self._observations: dict[str, Observation] = {}
        self._jobs: dict[str, AnalysisJob] = {}
        self._queue: deque[str] = deque()
        self._lock = Lock()

    def ping(self) -> bool:
        return True

    def replace_observations(self, observations: list[Observation]) -> int:
        with self._lock:
            self._observations = {item.date.isoformat(): item for item in observations}
        return len(self._observations)

    def list_observations(
        self, start: date | None = None, end: date | None = None
    ) -> list[Observation]:
        return sorted(
            (
                item
                for item in self._observations.values()
                if (start is None or item.date >= start) and (end is None or item.date <= end)
            ),
            key=lambda item: item.date,
        )

    def enqueue_analysis(self, request: AnalysisRequest) -> AnalysisJob:
        now = utc_now()
        job = AnalysisJob(
            id=str(uuid4()),
            request=request,
            status=JobStatus.SUBMITTED,
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            self._jobs[job.id] = job
            self._queue.append(job.id)
        return job

    def list_jobs(self) -> list[AnalysisJob]:
        return sorted(self._jobs.values(), key=lambda job: job.created_at, reverse=True)

    def get_job(self, job_id: str) -> AnalysisJob | None:
        return self._jobs.get(job_id)

    def claim_job(self, timeout_seconds: int = 0) -> str | None:
        del timeout_seconds
        with self._lock:
            return self._queue.popleft() if self._queue else None

    def save_job(self, job: AnalysisJob) -> None:
        with self._lock:
            self._jobs[job.id] = job


class RedisStore:
    _observations_key = "gas-price:observations"
    _observation_dates_key = "gas-price:observation-dates"
    _jobs_key = "gas-price:jobs"

    def __init__(self, client: Redis, *, queue_name: str) -> None:
        self.client = client
        self.queue_name = queue_name

    @classmethod
    def from_url(cls, redis_url: str, *, queue_name: str) -> RedisStore:
        return cls(Redis.from_url(redis_url, decode_responses=True), queue_name=queue_name)

    def ping(self) -> bool:
        return bool(self.client.ping())

    def replace_observations(self, observations: list[Observation]) -> int:
        if not observations:
            raise ValueError("cannot replace observations with an empty collection")

        with self.client.pipeline(transaction=True) as pipeline:
            pipeline.delete(self._observations_key, self._observation_dates_key)
            for observation in observations:
                key = observation.date.isoformat()
                pipeline.hset(self._observations_key, key, json.dumps(observation.to_dict()))
                pipeline.zadd(self._observation_dates_key, {key: observation.date.toordinal()})
            pipeline.execute()
        return len(observations)

    def list_observations(
        self, start: date | None = None, end: date | None = None
    ) -> list[Observation]:
        minimum = start.toordinal() if start else "-inf"
        maximum = end.toordinal() if end else "+inf"
        dates = self.client.zrangebyscore(self._observation_dates_key, minimum, maximum)
        if not dates:
            return []
        values = self.client.hmget(self._observations_key, dates)
        return [Observation.from_dict(json.loads(value)) for value in values if value is not None]

    def enqueue_analysis(self, request: AnalysisRequest) -> AnalysisJob:
        now = utc_now()
        job = AnalysisJob(
            id=str(uuid4()),
            request=request,
            status=JobStatus.SUBMITTED,
            created_at=now,
            updated_at=now,
        )
        with self.client.pipeline(transaction=True) as pipeline:
            pipeline.hset(self._jobs_key, job.id, json.dumps(job.to_dict()))
            pipeline.lpush(self.queue_name, job.id)
            pipeline.execute()
        return job

    def list_jobs(self) -> list[AnalysisJob]:
        jobs = [
            AnalysisJob.from_dict(json.loads(value)) for value in self.client.hvals(self._jobs_key)
        ]
        return sorted(jobs, key=lambda job: job.created_at, reverse=True)

    def get_job(self, job_id: str) -> AnalysisJob | None:
        value = self.client.hget(self._jobs_key, job_id)
        return AnalysisJob.from_dict(json.loads(value)) if value else None

    def claim_job(self, timeout_seconds: int = 0) -> str | None:
        claimed = self.client.brpop(self.queue_name, timeout=timeout_seconds)
        return claimed[1] if claimed else None

    def save_job(self, job: AnalysisJob) -> None:
        self.client.hset(self._jobs_key, job.id, json.dumps(job.to_dict()))
