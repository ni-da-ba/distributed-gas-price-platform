from __future__ import annotations

import json
from pathlib import Path

import pytest
import requests

from gas_price_platform.datasource import DataSourceError, OpenDataClient, parse_record

FIXTURE = Path(__file__).parent / "fixtures" / "open_data_sample.json"


class FakeResponse:
    def __init__(self, payload, status_code: int = 200) -> None:
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"status {self.status_code}")

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = iter(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return next(self.responses)


def fixture_records() -> list[dict]:
    return json.loads(FIXTURE.read_text())


def test_parse_record_normalizes_fields_and_omits_nulls() -> None:
    observation = parse_record(fixture_records()[1])

    assert observation.date.isoformat() == "2024-01-08"
    assert observation.prices == {"new-york-state": 3.2, "albany": 3.1}


def test_client_pages_until_short_response() -> None:
    records = fixture_records()
    session = FakeSession([FakeResponse(records[:2]), FakeResponse(records[2:])])
    client = OpenDataClient("https://example.test/data", page_size=2, session=session)

    observations = client.fetch_all()

    assert [item.date.isoformat() for item in observations] == [
        "2024-01-01",
        "2024-01-08",
        "2024-01-15",
    ]
    assert session.calls[1][1]["params"]["$offset"] == 2


def test_client_wraps_upstream_failure() -> None:
    client = OpenDataClient(
        "https://example.test/data", session=FakeSession([FakeResponse([], status_code=503)])
    )

    with pytest.raises(DataSourceError, match="request failed"):
        client.fetch_all()


def test_client_rejects_invalid_page_size_and_response_shapes() -> None:
    with pytest.raises(ValueError, match="page_size"):
        OpenDataClient("https://example.test/data", page_size=0)

    wrong_shape = OpenDataClient(
        "https://example.test/data", session=FakeSession([FakeResponse({"not": "a list"})])
    )
    with pytest.raises(DataSourceError, match="unexpected response shape"):
        wrong_shape.fetch_all()

    empty = OpenDataClient("https://example.test/data", session=FakeSession([FakeResponse([])]))
    with pytest.raises(DataSourceError, match="no observations"):
        empty.fetch_all()


def test_client_wraps_normalization_failure() -> None:
    client = OpenDataClient(
        "https://example.test/data",
        session=FakeSession([FakeResponse([{"date": "not-a-date", "albany_average_gal": "3"}])]),
    )

    with pytest.raises(DataSourceError, match="could not be normalized"):
        client.fetch_all()
