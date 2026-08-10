from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).parents[1]


def test_compose_separates_api_worker_and_redis() -> None:
    compose = yaml.safe_load((ROOT / "compose.yaml").read_text())

    assert set(compose["services"]) == {"api", "redis", "worker"}
    assert compose["services"]["api"]["ports"] == ["8000:8000"]
    assert compose["services"]["worker"]["command"] == [
        "python",
        "-m",
        "gas_price_platform.worker",
    ]
    assert (
        compose["services"]["api"]["environment"]["REDIS_URL"]
        == (compose["services"]["worker"]["environment"]["REDIS_URL"])
    )


def test_container_runs_application_as_non_root() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text()

    assert "USER 10001:10001" in dockerfile
    assert "--bind=0.0.0.0:8000" in dockerfile


def test_release_workflow_matches_kubernetes_image() -> None:
    workflow = (ROOT / ".github" / "workflows" / "publish-container.yml").read_text()
    api_manifest = (ROOT / "deploy" / "k8s" / "base" / "api.yaml").read_text()
    worker_manifest = (ROOT / "deploy" / "k8s" / "base" / "worker.yaml").read_text()
    image = "ghcr.io/ni-da-ba/distributed-gas-price-platform:1.0.0"

    assert 'tags: ["v*.*.*"]' in workflow
    assert '--tag "$IMAGE:$VERSION"' in workflow
    assert image in api_manifest
    assert image in worker_manifest
