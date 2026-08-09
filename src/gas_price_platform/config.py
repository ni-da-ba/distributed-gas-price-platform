"""Environment-backed application configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_REDIS_URL = "redis://localhost:6379/0"
DEFAULT_SOURCE_URL = "https://data.ny.gov/resource/nqur-w4p7.json"
DEFAULT_SOURCE_PAGE_SIZE = 1000
DEFAULT_SOURCE_TIMEOUT_SECONDS = 15.0
DEFAULT_QUEUE_NAME = "gas-price:analysis-queue"


@dataclass(frozen=True, slots=True)
class Settings:
    redis_url: str = DEFAULT_REDIS_URL
    source_url: str = DEFAULT_SOURCE_URL
    source_page_size: int = DEFAULT_SOURCE_PAGE_SIZE
    source_timeout_seconds: float = DEFAULT_SOURCE_TIMEOUT_SECONDS
    queue_name: str = DEFAULT_QUEUE_NAME

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            redis_url=os.getenv("REDIS_URL", DEFAULT_REDIS_URL),
            source_url=os.getenv("SOURCE_URL", DEFAULT_SOURCE_URL),
            source_page_size=int(os.getenv("SOURCE_PAGE_SIZE", str(DEFAULT_SOURCE_PAGE_SIZE))),
            source_timeout_seconds=float(
                os.getenv("SOURCE_TIMEOUT_SECONDS", str(DEFAULT_SOURCE_TIMEOUT_SECONDS))
            ),
            queue_name=os.getenv("QUEUE_NAME", DEFAULT_QUEUE_NAME),
        )
