from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "Prospect AI"
    assert body["environment"] == "test"


def test_health_sets_request_id_header(client: TestClient) -> None:
    response = client.get("/health")

    assert "x-request-id" in response.headers


def test_health_dependencies_reports_database_ok(client: TestClient) -> None:
    response = client.get("/health/dependencies")

    assert response.status_code == 200
    body = response.json()
    assert body["checks"]["database"] == "ok"


def test_health_dependencies_reports_redis_failure_without_masking_it(client: TestClient) -> None:
    """Nenhum servidor Redis real está disponível neste ambiente de teste
    (ver conftest.py). O endpoint deve reportar a falha explicitamente, não
    travar nem fingir que está tudo bem — coerente com o princípio de nunca
    converter "não verificado" em um estado positivo silencioso."""
    response = client.get("/health/dependencies")

    assert response.status_code == 200
    body = response.json()
    assert body["checks"]["redis"].startswith("error:")
    assert body["status"] == "degraded"
