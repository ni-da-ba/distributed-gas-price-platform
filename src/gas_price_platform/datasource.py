"""Open Data NY client and normalization logic."""

from __future__ import annotations

from datetime import date
from typing import Any

import requests

from .models import Observation

FIELD_TO_REGION = {
    "new_york_state_average_gal": "new-york-state",
    "albany_average_gal": "albany",
    "batavia_average_gal": "batavia",
    "binghamton_average_gal": "binghamton",
    "buffalo_average_gal": "buffalo",
    "dutchess_average_gal": "dutchess",
    "elmira_average_gal": "elmira",
    "glens_falls_average_gal": "glens-falls",
    "ithaca_average_gal": "ithaca",
    "kingston_average_gal": "kingston",
    "nassau_average_gal": "nassau",
    "new_york_city_average_gal": "new-york-city",
    "rochester_average_gal": "rochester",
    "syracuse_average_gal": "syracuse",
    "utica_average_gal": "utica",
    "watertown_average_gal": "watertown",
    "white_plains_average_gal": "white-plains",
}


class DataSourceError(RuntimeError):
    """Raised when upstream data cannot be fetched or normalized safely."""


class OpenDataClient:
    def __init__(
        self,
        base_url: str,
        *,
        page_size: int = 1000,
        timeout_seconds: float = 15.0,
        session: requests.Session | None = None,
    ) -> None:
        if page_size <= 0:
            raise ValueError("page_size must be positive")
        self.base_url = base_url
        self.page_size = page_size
        self.timeout_seconds = timeout_seconds
        self.session = session or requests.Session()

    def fetch_all(self) -> list[Observation]:
        records: list[dict[str, Any]] = []
        offset = 0

        while True:
            try:
                response = self.session.get(
                    self.base_url,
                    params={"$limit": self.page_size, "$offset": offset, "$order": "date ASC"},
                    timeout=self.timeout_seconds,
                )
                response.raise_for_status()
                page = response.json()
            except (requests.RequestException, ValueError) as exc:
                raise DataSourceError("Open Data NY request failed") from exc

            if not isinstance(page, list):
                raise DataSourceError("Open Data NY returned an unexpected response shape")
            records.extend(page)
            if len(page) < self.page_size:
                break
            offset += self.page_size

        try:
            observations = [parse_record(record) for record in records]
        except (KeyError, TypeError, ValueError) as exc:
            raise DataSourceError("Open Data NY response could not be normalized") from exc

        if not observations:
            raise DataSourceError("Open Data NY returned no observations")
        return sorted(observations, key=lambda observation: observation.date)


def parse_record(record: dict[str, Any]) -> Observation:
    observed_on = date.fromisoformat(str(record["date"])[:10])
    prices = {
        region: float(record[field])
        for field, region in FIELD_TO_REGION.items()
        if record.get(field) not in (None, "")
    }
    return Observation(date=observed_on, prices=prices)
