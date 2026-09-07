"""Testes de `enqueue_or_run_*` (Prompt 10, seção 3 — auditoria de
cobertura): o caminho "Redis disponível → retorna 'queued'" nunca havia
sido exercitado em `app/domains/{discovery,audit,briefing}/jobs.py`, já
que Redis está sempre indisponível nesta suíte — todo teste de rota HTTP
sempre cai no fallback síncrono (`db is not None`), nunca no caminho de
enfileiramento de verdade.

**O que continua sem cobertura de unidade, deliberadamente**: o CORPO de
`run_discovery_search`/`run_digital_audit`/`run_sales_brief` (a função que
abre sua PRÓPRIA `SessionLocal`, pensada para rodar em um processo de
worker separado) — testá-la diretamente exigiria ou (a) deixá-la commitar
de verdade no arquivo SQLite compartilhado da suíte, vazando estado entre
testes (quebrando o isolamento que `db_session`/`conftest.py` garante para
todo o resto da suíte), ou (b) um monkeypatch de `SessionLocal` complexo o
suficiente para introduzir seu próprio risco de mascarar um bug real. A
lógica que essas funções chamam (`DiscoveryService.execute`,
`DigitalAuditService.execute`, `SalesBriefService.generate`) já é
extensivamente testada via o outro branch de `enqueue_or_run_*`
(`db is not None`, o caminho usado por toda rota HTTP) — o que falta
cobrir é só a abertura da sessão própria, cujo mecanismo genérico
(RQ executando uma função por referência de módulo) já é provado por
`tests/jobs/test_worker_integration.py` (F8.2), com fixtures diferentes.
"""
from __future__ import annotations

import uuid

import fakeredis
import pytest


@pytest.fixture
def fake_redis_connection(monkeypatch: pytest.MonkeyPatch):
    connection = fakeredis.FakeStrictRedis()
    monkeypatch.setattr("app.jobs.queue.get_redis_connection", lambda: connection)
    return connection


class TestEnqueueOrRunDiscovery:
    def test_returns_queued_and_enqueues_the_real_job_function_when_redis_is_available(
        self, fake_redis_connection
    ) -> None:
        from app.domains.discovery.jobs import QUEUE_NAME, enqueue_or_run_discovery, run_discovery_search

        search_run_id = uuid.uuid4()
        result = enqueue_or_run_discovery(search_run_id, db=None)

        assert result == "queued"
        from rq import Queue

        queue = Queue(QUEUE_NAME, connection=fake_redis_connection)
        assert queue.count == 1
        job = queue.jobs[0]
        assert job.func == run_discovery_search
        assert job.args == (str(search_run_id),)


class TestEnqueueOrRunAudit:
    def test_returns_queued_and_enqueues_the_real_job_function_when_redis_is_available(
        self, fake_redis_connection
    ) -> None:
        from app.domains.audit.jobs import QUEUE_NAME, enqueue_or_run_audit, run_digital_audit

        snapshot_id = uuid.uuid4()
        result = enqueue_or_run_audit(snapshot_id, db=None)

        assert result == "queued"
        from rq import Queue

        queue = Queue(QUEUE_NAME, connection=fake_redis_connection)
        assert queue.count == 1
        assert queue.jobs[0].func == run_digital_audit


class TestEnqueueOrRunSalesBrief:
    def test_returns_queued_and_enqueues_the_real_job_function_when_redis_is_available(
        self, fake_redis_connection
    ) -> None:
        from app.domains.briefing.jobs import QUEUE_NAME, enqueue_or_run_sales_brief, run_sales_brief

        company_id = uuid.uuid4()
        result = enqueue_or_run_sales_brief(company_id, db=None)

        assert result == "queued"
        from rq import Queue

        queue = Queue(QUEUE_NAME, connection=fake_redis_connection)
        assert queue.count == 1
        assert queue.jobs[0].func == run_sales_brief


class TestEnqueueOrRunPrototypeGeneration:
    def test_returns_queued_and_enqueues_the_real_job_function_when_redis_is_available(
        self, fake_redis_connection
    ) -> None:
        from app.domains.prototypes.jobs import (
            QUEUE_NAME,
            enqueue_or_run_prototype_generation,
            run_prototype_generation,
        )

        generation_run_id = uuid.uuid4()
        result = enqueue_or_run_prototype_generation(generation_run_id, db=None)

        assert result == "queued"
        from rq import Queue

        queue = Queue(QUEUE_NAME, connection=fake_redis_connection)
        assert queue.count == 1
        assert queue.jobs[0].func == run_prototype_generation
