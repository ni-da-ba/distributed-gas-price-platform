from __future__ import annotations

from datetime import date

import pytest

from gas_price_platform.analytics import analyze_region, linear_trend, regional_series, summarize
from gas_price_platform.models import Observation


def test_regional_series_filters_and_orders() -> None:
    observations = [
        Observation(date(2024, 1, 15), {"albany": 3.2}),
        Observation(date(2024, 1, 1), {"albany": 3.0}),
        Observation(date(2024, 1, 8), {"other": 9.9}),
    ]

    assert regional_series(observations, "albany") == [
        (date(2024, 1, 1), 3.0),
        (date(2024, 1, 15), 3.2),
    ]


def test_summary_reports_population_statistics() -> None:
    result = summarize([(date(2024, 1, 1), 3.0), (date(2024, 1, 8), 3.1), (date(2024, 1, 15), 3.2)])

    assert result["count"] == 3
    assert result["mean_usd_per_gallon"] == pytest.approx(3.1)
    assert result["population_stddev_usd_per_gallon"] == pytest.approx(0.081649658)
    assert result["minimum"] == {"date": "2024-01-01", "value": 3.0}
    assert result["maximum"] == {"date": "2024-01-15", "value": 3.2}


def test_linear_trend_uses_weeks_and_reports_perfect_fit() -> None:
    result = linear_trend(
        [(date(2024, 1, 1), 3.0), (date(2024, 1, 8), 3.1), (date(2024, 1, 15), 3.2)]
    )

    assert result["slope_usd_per_gallon_per_week"] == pytest.approx(0.1)
    assert result["intercept_usd_per_gallon"] == pytest.approx(3.0)
    assert result["r_squared"] == pytest.approx(1.0)


def test_analysis_rejects_empty_series(observations: list[Observation]) -> None:
    with pytest.raises(ValueError, match="no observations"):
        analyze_region(observations, "missing")
