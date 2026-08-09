from __future__ import annotations

from pathlib import Path

import yaml

BASE = Path(__file__).parents[1] / "deploy" / "k8s" / "base"


def resources() -> list[dict]:
    documents = []
    for path in BASE.glob("*.yaml"):
        if path.name == "kustomization.yaml":
            continue
        documents.extend(document for document in yaml.safe_load_all(path.read_text()) if document)
    return documents


def test_expected_kubernetes_workloads_and_services_exist() -> None:
    identities = {(item["kind"], item["metadata"]["name"]) for item in resources()}

    assert ("Deployment", "gas-price-api") in identities
    assert ("Deployment", "gas-price-worker") in identities
    assert ("Deployment", "redis") in identities
    assert ("Service", "gas-price-api") in identities
    assert ("Service", "redis") in identities


def test_application_workloads_are_non_root_and_bounded() -> None:
    deployments = {
        item["metadata"]["name"]: item for item in resources() if item["kind"] == "Deployment"
    }

    for name in ("gas-price-api", "gas-price-worker"):
        pod_spec = deployments[name]["spec"]["template"]["spec"]
        assert pod_spec["securityContext"]["runAsNonRoot"] is True
        container = pod_spec["containers"][0]
        assert container["securityContext"]["allowPrivilegeEscalation"] is False
        assert container["securityContext"]["readOnlyRootFilesystem"] is True
        assert container["securityContext"]["capabilities"]["drop"] == ["ALL"]
        assert set(container["resources"]) == {"requests", "limits"}


def test_api_has_distinct_liveness_and_readiness_probes() -> None:
    api = next(
        item
        for item in resources()
        if item["kind"] == "Deployment" and item["metadata"]["name"] == "gas-price-api"
    )
    container = api["spec"]["template"]["spec"]["containers"][0]

    assert container["livenessProbe"]["httpGet"]["path"] == "/health/live"
    assert container["readinessProbe"]["httpGet"]["path"] == "/health/ready"


def test_manifests_contain_no_secret_objects() -> None:
    assert all(item["kind"] != "Secret" for item in resources())
