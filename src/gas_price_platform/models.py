"""Domain objects shared by the API, store, and worker."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class Observation:
    date: date
    prices: dict[str, float]

    def __post_init__(self) -> None:
        if not self.prices:
            raise ValueError("an observation must contain at least one regional price")
        if any((not math.isfinite(value) or value <= 0) for value in self.prices.values()):
            raise ValueError("prices must be finite positive numbers")

    def to_dict(self) -> dict[str, Any]:
        return {"date": self.date.isoformat(), "prices": dict(sorted(self.prices.items()))}

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Observation:
        return cls(
            date=date.fromisoformat(value["date"]),
            prices={key: float(price) for key, price in value["prices"].items()},
        )


@dataclass(frozen=True, slots=True)
class AnalysisRequest:
    region: str
    start: date | None = None
    end: date | None = None

    def __post_init__(self) -> None:
        if not self.region:
            raise ValueError("region is required")
        if self.start and self.end and self.start > self.end:
            raise ValueError("start must not be after end")

    def to_dict(self) -> dict[str, str | None]:
        return {
            "region": self.region,
            "start": self.start.isoformat() if self.start else None,
            "end": self.end.isoformat() if self.end else None,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> AnalysisRequest:
        return cls(
            region=value["region"],
            start=date.fromisoformat(value["start"]) if value.get("start") else None,
            end=date.fromisoformat(value["end"]) if value.get("end") else None,
        )


class JobStatus(StrEnum):
    SUBMITTED = "submitted"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass(slots=True)
class AnalysisJob:
    id: str
    request: AnalysisRequest
    status: JobStatus
    created_at: datetime
    updated_at: datetime
    result: dict[str, Any] | None = None
    error: str | None = None

    def to_dict(self, *, include_result: bool = True) -> dict[str, Any]:
        value: dict[str, Any] = {
            "id": self.id,
            "request": self.request.to_dict(),
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "error": self.error,
        }
        if include_result:
            value["result"] = self.result
        return value

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> AnalysisJob:
        return cls(
            id=value["id"],
            request=AnalysisRequest.from_dict(value["request"]),
            status=JobStatus(value["status"]),
            created_at=datetime.fromisoformat(value["created_at"]),
            updated_at=datetime.fromisoformat(value["updated_at"]),
            result=value.get("result"),
            error=value.get("error"),
        )
