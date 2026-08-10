"""Flask application factory and versioned HTTP routes."""

from __future__ import annotations

from datetime import date
from http import HTTPStatus
from typing import Any

from flask import Flask, jsonify, request
from redis.exceptions import RedisError

from .analytics import regional_series, summarize
from .config import Settings
from .datasource import DataSourceError, OpenDataClient
from .models import AnalysisRequest, JobStatus
from .store import RedisStore, Store


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def create_app(
    settings: Settings | None = None,
    *,
    store: Store | None = None,
    data_source: OpenDataClient | None = None,
) -> Flask:
    app = Flask(__name__)
    resolved_settings = settings or Settings.from_env()
    resolved_store = store or RedisStore.from_url(
        resolved_settings.redis_url, queue_name=resolved_settings.queue_name
    )
    resolved_source = data_source or OpenDataClient(
        resolved_settings.source_url,
        page_size=resolved_settings.source_page_size,
        timeout_seconds=resolved_settings.source_timeout_seconds,
    )

    @app.errorhandler(ApiError)
    def handle_api_error(error: ApiError) -> tuple[Any, int]:
        return jsonify({"error": {"code": error.code, "message": error.message}}), error.status

    @app.errorhandler(RedisError)
    def handle_redis_error(_error: RedisError) -> tuple[Any, int]:
        return (
            jsonify(
                {
                    "error": {
                        "code": "storage_unavailable",
                        "message": "Redis is unavailable",
                    }
                }
            ),
            HTTPStatus.SERVICE_UNAVAILABLE,
        )

    @app.get("/health/live")
    def live() -> tuple[Any, int]:
        return jsonify({"status": "live"}), HTTPStatus.OK

    @app.get("/health/ready")
    def ready() -> tuple[Any, int]:
        if not resolved_store.ping():
            raise ApiError(HTTPStatus.SERVICE_UNAVAILABLE, "not_ready", "Redis is unavailable")
        return jsonify({"status": "ready"}), HTTPStatus.OK

    @app.post("/v1/data/refresh")
    def refresh_data() -> tuple[Any, int]:
        try:
            observations = resolved_source.fetch_all()
        except DataSourceError as exc:
            raise ApiError(HTTPStatus.BAD_GATEWAY, "upstream_unavailable", str(exc)) from exc
        count = resolved_store.replace_observations(observations)
        return jsonify({"observations_stored": count}), HTTPStatus.OK

    @app.get("/v1/regions")
    def list_regions() -> tuple[Any, int]:
        observations = resolved_store.list_observations()
        regions = sorted({region for item in observations for region in item.prices})
        return jsonify({"regions": regions}), HTTPStatus.OK

    @app.get("/v1/prices")
    def prices() -> tuple[Any, int]:
        region = required_region()
        start, end = requested_interval()
        observations = resolved_store.list_observations(start, end)
        series = regional_series(observations, region, start, end)
        if not series:
            raise ApiError(
                HTTPStatus.NOT_FOUND,
                "series_not_found",
                "No observations match the requested region and interval",
            )
        return (
            jsonify(
                {
                    "region": region,
                    "observations": [
                        {"date": observed_on.isoformat(), "usd_per_gallon": value}
                        for observed_on, value in series
                    ],
                }
            ),
            HTTPStatus.OK,
        )

    @app.get("/v1/summary")
    def summary() -> tuple[Any, int]:
        region = required_region()
        start, end = requested_interval()
        series = regional_series(resolved_store.list_observations(start, end), region, start, end)
        try:
            result = summarize(series)
        except ValueError as exc:
            raise ApiError(HTTPStatus.NOT_FOUND, "series_not_found", str(exc)) from exc
        return jsonify({"region": region, "summary": result}), HTTPStatus.OK

    @app.post("/v1/jobs/region-analysis")
    def create_analysis_job() -> tuple[Any, int]:
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            raise ApiError(HTTPStatus.BAD_REQUEST, "invalid_json", "A JSON object is required")
        region = body.get("region")
        if not isinstance(region, str) or not region.strip():
            raise ApiError(HTTPStatus.BAD_REQUEST, "invalid_region", "region is required")
        start = parse_date(body.get("start"), "start")
        end = parse_date(body.get("end"), "end")
        try:
            analysis_request = AnalysisRequest(region=region.strip().lower(), start=start, end=end)
        except ValueError as exc:
            raise ApiError(HTTPStatus.BAD_REQUEST, "invalid_interval", str(exc)) from exc
        job = resolved_store.enqueue_analysis(analysis_request)
        return jsonify(job.to_dict(include_result=False)), HTTPStatus.ACCEPTED

    @app.get("/v1/jobs")
    def list_jobs() -> tuple[Any, int]:
        jobs = [job.to_dict(include_result=False) for job in resolved_store.list_jobs()]
        return jsonify({"jobs": jobs}), HTTPStatus.OK

    @app.get("/v1/jobs/<job_id>")
    def get_job(job_id: str) -> tuple[Any, int]:
        job = require_job(resolved_store, job_id)
        return jsonify(job.to_dict(include_result=False)), HTTPStatus.OK

    @app.get("/v1/jobs/<job_id>/result")
    def get_result(job_id: str) -> tuple[Any, int]:
        job = require_job(resolved_store, job_id)
        if job.status is not JobStatus.COMPLETE:
            raise ApiError(
                HTTPStatus.CONFLICT,
                "job_not_complete",
                f"Job status is {job.status.value}",
            )
        return jsonify({"id": job.id, "result": job.result}), HTTPStatus.OK

    return app


def required_region() -> str:
    region = request.args.get("region", "").strip().lower()
    if not region:
        raise ApiError(
            HTTPStatus.BAD_REQUEST, "invalid_region", "region query parameter is required"
        )
    return region


def requested_interval() -> tuple[date | None, date | None]:
    start = parse_date(request.args.get("start"), "start")
    end = parse_date(request.args.get("end"), "end")
    if start and end and start > end:
        raise ApiError(HTTPStatus.BAD_REQUEST, "invalid_interval", "start must not be after end")
    return start, end


def parse_date(value: Any, field: str) -> date | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise ApiError(HTTPStatus.BAD_REQUEST, "invalid_date", f"{field} must be an ISO date")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ApiError(
            HTTPStatus.BAD_REQUEST, "invalid_date", f"{field} must use YYYY-MM-DD"
        ) from exc


def require_job(store: Store, job_id: str):
    job = store.get_job(job_id)
    if job is None:
        raise ApiError(HTTPStatus.NOT_FOUND, "job_not_found", "Job does not exist")
    return job
