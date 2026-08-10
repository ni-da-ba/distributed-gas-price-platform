from __future__ import annotations

from datetime import date

import pytest

from gas_price_platform.models import Observation
from gas_price_platform.store import MemoryStore


@pytest.fixture
def observations() -> list[Observation]:
    return [
        Observation(date(2024, 1, 1), {"albany": 3.0, "new-york-state": 3.1}),
        Observation(date(2024, 1, 8), {"albany": 3.1, "new-york-state": 3.2}),
        Observation(date(2024, 1, 15), {"albany": 3.2, "new-york-state": 3.3}),
    ]


@pytest.fixture
def memory_store(observations: list[Observation]) -> MemoryStore:
    store = MemoryStore()
    store.replace_observations(observations)
    return store
