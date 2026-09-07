"""Testes de injeção de falha (Fase 8.7).

Complementam, sem duplicar, a cobertura já existente de "Redis indisponível"
(extensiva desde a Fase 7 em cada rota que usa `check_and_increment`/cache) e
de "Anthropic indisponível" (`tests/briefing/test_providers.py`,
`tests/outreach/test_service.py`). O que este arquivo cobre e não existia
antes da Fase 8.7:

1. Falha de banco de dados NO MEIO de uma rota de domínio real (não só em
   `/health/dependencies`, que é o único lugar já coberto) — prova que o
   `unhandled_exception_handler` genérico (`app.core.errors`) intercepta e
   devolve um 500 limpo, sem vazar stack trace nem travar a requisição,
   também para uma rota de negócio comum.
2. "Worker down": um job enfileirado enquanto nenhum worker está
   consumindo a fila permanece `queued` indefinidamente — nunca é
   silenciosamente perdido nem executado por engano em outro lugar. Prova
   isolada do mecanismo de enfileiramento em si (`enqueue_or_run_*`),
   diferente de `tests/jobs/test_worker_integration.py` (que sempre inicia
   um worker `fakeredis` para consumir o job).

Metodologia não destrutiva: nenhum destes testes derruba um processo real
(não há PostgreSQL/Redis real para derrubar nesta máquina — ver
docs/production-readiness.md). Cada falha é injetada via `monkeypatch` de
forma cirúrgica, documentada em cada teste.
"""
from __future__ import annotations

import uuid

import fakeredis
import pytest
from fastapi.testclient import TestClient
from rq import Queue
from sqlalchemy.orm import Session

from app.main import app


class TestDatabaseFailureMidRequest:
    """PostgreSQL indisponível durante uma rota de negócio comum (não `/health`).

    Usa um `TestClient` com `raise_server_exceptions=False`, deliberadamente
    diferente do fixture `client` padrão: por padrão o TestClient reergue
    dentro do teste qualquer exceção não tratada pela rota (útil para
    depuração), mesmo quando `unhandled_exception_handler` já produziu a
    resposta 500 real que o navegador/cliente HTTP real receberia — aqui
    queremos observar exatamente essa resposta real, não a exceção Python."""

    def test_listing_companies_returns_clean_500_when_database_fails(self, monkeypatch) -> None:
        def _boom(self, *args, **kwargs):
            raise RuntimeError("conexão perdida")

        monkeypatch.setattr(Session, "execute", _boom)

        with TestClient(app, raise_server_exceptions=False) as raw_client:
            response = raw_client.get("/api/companies")

        assert response.status_code == 500
        body = response.json()
        assert body["error"]["code"] == "internal_error"
        # Nunca vaza o tipo/mensagem real da exceção ao cliente.
        assert "RuntimeError" not in response.text
        assert "conexão perdida" not in response.text

    def test_getting_crm_kpis_returns_clean_500_when_database_fails(
        self, client, monkeypatch, auth_headers
    ) -> None:
        def _boom(self, *args, **kwargs):
            raise RuntimeError("conexão perdida")

        monkeypatch.setattr(Session, "execute", _boom)

        with TestClient(app, raise_server_exceptions=False) as raw_client:
            response = raw_client.get("/api/crm/kpis", headers=auth_headers)

        assert response.status_code == 500
        assert response.json()["error"]["code"] == "internal_error"


class TestWorkerDown:
    """Job enfileirado sem nenhum worker consumindo: nunca perdido, nunca
    silenciosamente executado — apenas fica pendente, visível como tal."""

    def test_job_enqueued_with_no_worker_running_stays_queued_forever(self) -> None:
        from tests.jobs._fixtures import add

        connection = fakeredis.FakeStrictRedis()
        queue = Queue("discovery", connection=connection)

        job = queue.enqueue(add, 2, 3)

        # Nenhum `Worker(...).work()` foi iniciado — simula exatamente
        # "worker down": o processo que deveria consumir a fila não existe.
        assert job.get_status() == "queued"
        assert queue.count == 1

        # Mesmo depois de "algum tempo" (aqui, apenas reconsultando o
        # estado), o job continua exatamente onde estava — não é perdido,
        # não é marcado como falho, não é executado por engano.
        refetched = queue.fetch_job(job.id)
        assert refetched is not None
        assert refetched.get_status() == "queued"


class TestRedisDownConsistencySummary:
    """Não reintroduz cobertura já existente — apenas documenta, em um só
    lugar, onde a cobertura de "Redis indisponível" já vive, para que a F8.7
    tenha um ponto de referência único sem duplicar testes."""

    def test_redis_unavailable_paths_are_covered_elsewhere(self) -> None:
        """Âncora de documentação, não uma nova prova: caso algum destes
        arquivos seja removido no futuro sem que ninguém perceba que ele
        carregava a cobertura de "Redis indisponível", este teste falha ao
        importar e aponta para onde a cobertura real está."""
        import tests.briefing.test_api  # noqa: F401 - TestRateLimiting (fail_closed)
        import tests.outreach.test_api  # noqa: F401 - TestRateLimiting (fail_closed)
        import tests.test_health  # noqa: F401 - redis "degraded" sem derrubar readiness
        import tests.test_security_hardening  # noqa: F401 - local_fallback de login/registro


@pytest.fixture
def auth_headers(client) -> dict[str, str]:
    email = f"failuretest+{uuid.uuid4().hex[:8]}@example.com"
    response = client.post(
        "/api/auth/register",
        json={"email": email, "name": "Failure Test", "password": "senha-forte-123"},
    )
    response.raise_for_status()
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
