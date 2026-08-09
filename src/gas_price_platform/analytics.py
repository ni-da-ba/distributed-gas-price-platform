"""Deterministic descriptive statistics and least-squares trend analysis."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from statistics import fmean, pstdev
from typing import Any

from .models import Observation


def regional_series(
    observations: Iterable[Observation],
    region: str,
    start: date | None = None,
    end: date | None = None,
) -> list[tuple[date, float]]:
    series = [
        (observation.date, observation.prices[region])
        for observation in observations
        if region in observation.prices
        and (start is None or observation.date >= start)
        and (end is None or observation.date <= end)
    ]
    return sorted(series)


def summarize(series: list[tuple[date, float]]) -> dict[str, Any]:
    if not series:
        raise ValueError("no observations match the requested region and interval")

    values = [value for _, value in series]
    return {
        "count": len(values),
        "mean_usd_per_gallon": fmean(values),
        "population_stddev_usd_per_gallon": pstdev(values),
        "minimum": {
            "date": min(series, key=lambda item: item[1])[0].isoformat(),
            "value": min(values),
        },
        "maximum": {
            "date": max(series, key=lambda item: item[1])[0].isoformat(),
            "value": max(values),
        },
    }


def linear_trend(series: list[tuple[date, float]]) -> dict[str, float | str]:
    if not series:
        raise ValueError("at least one observation is required")

    origin = series[0][0]
    x = [(current_date - origin).days / 7.0 for current_date, _ in series]
    y = [value for _, value in series]

    if len(series) == 1 or all(value == x[0] for value in x):
        return {
            "origin_date": origin.isoformat(),
            "slope_usd_per_gallon_per_week": 0.0,
            "intercept_usd_per_gallon": y[0],
            "r_squared": 1.0,
        }

    x_mean = fmean(x)
    y_mean = fmean(y)
    denominator = sum((value - x_mean) ** 2 for value in x)
    slope = (
        sum((x_value - x_mean) * (y_value - y_mean) for x_value, y_value in zip(x, y, strict=True))
        / denominator
    )
    intercept = y_mean - slope * x_mean
    residual = sum(
        (y_value - (intercept + slope * x_value)) ** 2
        for x_value, y_value in zip(x, y, strict=True)
    )
    total = sum((value - y_mean) ** 2 for value in y)
    r_squared = 1.0 if total == 0 else 1.0 - residual / total

    return {
        "origin_date": origin.isoformat(),
        "slope_usd_per_gallon_per_week": slope,
        "intercept_usd_per_gallon": intercept,
        "r_squared": r_squared,
    }


def analyze_region(
    observations: Iterable[Observation],
    region: str,
    start: date | None = None,
    end: date | None = None,
) -> dict[str, Any]:
    series = regional_series(observations, region, start, end)
    return {
        "region": region,
        "interval": {
            "start": start.isoformat() if start else None,
            "end": end.isoformat() if end else None,
        },
        "summary": summarize(series),
        "linear_trend": linear_trend(series),
    }
