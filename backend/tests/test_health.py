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
    assert body["status"] == "ok"


def test_health_dependencies_reports_redis_failure_without_masking_it(client: TestClient) -> None:
    """Nenhum servidor Redis real está disponível neste ambiente de teste
    (ver conftest.py). O endpoint deve reportar a falha explicitamente, não
    travar nem fingir que está tudo bem — coerente com o princípio de nunca
    converter "não verificado" em um estado positivo silencioso.

    Desde a Fase 8.6 (semântica formal de liveness/readiness, achado da
    auditoria F8.0 seção 12), Redis indisponível NUNCA torna a aplicação
    "not ready" — é best-effort em todo o resto do sistema por desenho
    (fila com fallback síncrono, cache, rate limiting fail-closed/
    local-fallback). O `status` HTTP continua 200; só PostgreSQL
    indisponível derruba a readiness (ver teste abaixo)."""
    response = client.get("/health/dependencies")

    assert response.status_code == 200
    body = response.json()
    assert body["checks"]["redis"].startswith("degraded:")
    assert body["status"] == "ok"


def test_health_dependencies_reports_anthropic_configuration_without_a_network_call(client: TestClient) -> None:
    """Nenhuma ANTHROPIC_API_KEY está configurada no ambiente de teste (ver
    tests/conftest.py) — o endpoint reporta isso sem NUNCA fazer uma
    chamada de rede real (uma probe de readiness chamada a cada poucos
    segundos por um orquestrador não pode ter custo de API a cada
    execução)."""
    response = client.get("/health/dependencies")

    assert response.status_code == 200
    assert response.json()["checks"]["anthropic"] == "not_configured"


def test_health_dependencies_returns_503_and_not_ready_when_database_is_unreachable(client: TestClient, monkeypatch) -> None:
    """PostgreSQL é a ÚNICA dependência que determina readiness — simulamos
    a falha diretamente na execução da query, sem depender de derrubar um
    banco real."""
    from sqlalchemy.orm import Session

    def _boom(self, *args, **kwargs):
        raise RuntimeError("conexão perdida")

    monkeypatch.setattr(Session, "execute", _boom)

    response = client.get("/health/dependencies")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["checks"]["database"].startswith("error:")
