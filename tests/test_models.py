from __future__ import annotations

from datetime import date

import pytest

from gas_price_platform.models import AnalysisRequest, Observation


def test_observation_validation() -> None:
    with pytest.raises(ValueError, match="at least one"):
        Observation(date(2024, 1, 1), {})
    with pytest.raises(ValueError, match="positive"):
        Observation(date(2024, 1, 1), {"albany": 0.0})


def test_analysis_request_validation() -> None:
    with pytest.raises(ValueError, match="region"):
        AnalysisRequest(region="")
    with pytest.raises(ValueError, match="start"):
        AnalysisRequest(region="albany", start=date(2024, 2, 1), end=date(2024, 1, 1))
