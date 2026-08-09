"""Exercise the API, Redis, and worker through the running Compose stack."""

from __future__ import annotations

import json
import subprocess
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

BASE_URL = "http://127.0.0.1:8000"


def request_json(path: str, *, payload: dict | None = None) -> tuple[int, dict]:
    body = json.dumps(payload).encode() if payload is not None else None
    request = Request(
        BASE_URL + path,
        data=body,
        headers={"Content-Type": "application/json"} if body else {},
        method="POST" if body else "GET",
    )
    try:
        with urlopen(request, timeout=5) as response:
            return response.status, json.load(response)
    except HTTPError as error:
        return error.code, json.load(error)


def seed_observations() -> None:
    code = """
from datetime import date
from gas_price_platform.config import Settings
from gas_price_platform.models import Observation
from gas_price_platform.store import RedisStore

settings = Settings.from_env()
store = RedisStore.from_url(settings.redis_url, queue_name=settings.queue_name)
store.replace_observations([
    Observation(date(2024, 1, 1), {"albany": 3.0}),
    Observation(date(2024, 1, 8), {"albany": 3.1}),
    Observation(date(2024, 1, 15), {"albany": 3.2}),
])
"""
    subprocess.run(
        ["docker", "compose", "exec", "-T", "api", "python", "-c", code],
        check=True,
    )


def main() -> None:
    status, readiness = request_json("/health/ready")
    assert status == 200 and readiness == {"status": "ready"}

    seed_observations()
    status, job = request_json("/v1/jobs/region-analysis", payload={"region": "albany"})
    assert status == 202

    result = None
    for _ in range(40):
        status, response = request_json(f"/v1/jobs/{job['id']}/result")
        if status == 200:
            result = response["result"]
            break
        assert status == 409
        time.sleep(0.25)

    assert result is not None, "worker did not complete the analysis within 10 seconds"
    assert result["summary"]["count"] == 3
    assert abs(result["linear_trend"]["slope_usd_per_gallon_per_week"] - 0.1) < 1e-12
    print("Compose smoke test passed: API -> Redis queue -> worker -> result")


if __name__ == "__main__":
    main()
