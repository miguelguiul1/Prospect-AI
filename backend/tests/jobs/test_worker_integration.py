"""Prova, pela primeira vez no projeto (Fase 8.2), que o mecanismo
enqueue → worker → execução realmente funciona — não só por revisão de
código (achado da auditoria F8.0, seção 10: nenhum worker jamais existiu).

Usa `fakeredis` (dependência de teste, não de produção — ver
`requirements-dev.txt`) em vez de Redis real, porque nenhuma máquina usada
neste projeto até aqui tem Redis disponível. Isto é **VALIDADO COM MOCK**,
explicitamente — não confundir com Redis real (ver `tests/infra/
test_real_redis.py`, que só executa contra Redis de verdade e é pulado
aqui). `fakeredis` implementa o protocolo Redis o suficiente para RQ
funcionar de ponta a ponta (enqueue, BLPOP interno, registries), o que
nenhuma suposição substituiria com a mesma confiança.
"""
from __future__ import annotations

import fakeredis
import pytest
from rq import Queue, SimpleWorker
from rq.job import JobStatus

from app.worker import DEFAULT_QUEUES
from tests.jobs import _fixtures


@pytest.fixture()
def fake_redis_connection():
    return fakeredis.FakeStrictRedis()


class TestEnqueueWorkerRoundtrip:
    def test_a_queued_job_is_actually_executed_by_a_worker(self, fake_redis_connection) -> None:
        queue = Queue("testq", connection=fake_redis_connection)
        job = queue.enqueue(_fixtures.add, 2, 3)
        assert job.get_status() == JobStatus.QUEUED

        worker = SimpleWorker(["testq"], connection=fake_redis_connection)
        worker.work(burst=True)  # burst=True: processa o que já está na fila e sai — sem loop infinito no teste

        job.refresh()
        assert job.get_status() == JobStatus.FINISHED
        assert job.return_value() == 5

    def test_a_worker_only_listening_to_a_different_queue_never_picks_up_the_job(self, fake_redis_connection) -> None:
        """Prova que um worker respeita a lista de filas que recebeu — um
        job em `discovery` nunca deveria ser processado por um worker
        configurado só para `briefing`, por exemplo."""
        queue = Queue("real_queue", connection=fake_redis_connection)
        job = queue.enqueue(_fixtures.add, 1, 1)

        worker = SimpleWorker(["outra_fila_qualquer"], connection=fake_redis_connection)
        worker.work(burst=True)

        job.refresh()
        assert job.get_status() == JobStatus.QUEUED  # ninguém processou


class TestFailureHandling:
    def test_a_job_that_raises_is_marked_failed_not_silently_lost(self, fake_redis_connection) -> None:
        queue = Queue("testq", connection=fake_redis_connection)
        job = queue.enqueue(_fixtures.raise_value_error, "algo deu errado")

        worker = SimpleWorker(["testq"], connection=fake_redis_connection)
        worker.work(burst=True)

        job.refresh()
        assert job.get_status() == JobStatus.FAILED
        result = job.latest_result()
        assert result is not None
        assert "algo deu errado" in result.exc_string

    def test_no_automatic_retry_by_default(self, fake_redis_connection) -> None:
        """Nenhum domínio deste projeto configura retry (decisão deliberada
        documentada em cada `app/domains/*/jobs.py`) — confirma que, sem
        `retry=` explícito no `enqueue()`, o job falho realmente para na
        primeira tentativa, nunca reexecuta sozinho."""
        queue = Queue("testq", connection=fake_redis_connection)
        job = queue.enqueue(_fixtures.raise_value_error, "falha única")

        worker = SimpleWorker(["testq"], connection=fake_redis_connection)
        worker.work(burst=True)

        job.refresh()
        assert job.get_status() == JobStatus.FAILED
        # `retries_left` é None quando nenhuma política de retry foi configurada.
        assert job.retries_left in (None, 0)


class TestWorkerQueueConsistency:
    """Evita exatamente a classe de bug que motivou este módulo: alguém
    renomeia/adiciona uma fila em um domínio e esquece de atualizar
    `app.worker.DEFAULT_QUEUES` — o job passaria a ficar preso para sempre,
    silenciosamente, mesmo com o worker rodando."""

    def test_worker_listens_to_exactly_the_three_real_queues(self) -> None:
        assert set(DEFAULT_QUEUES) == {"discovery", "audit", "briefing"}

    def test_each_domain_queue_name_matches_what_the_worker_expects(self) -> None:
        from app.domains.audit.jobs import QUEUE_NAME as audit_queue
        from app.domains.briefing.jobs import QUEUE_NAME as briefing_queue
        from app.domains.discovery.jobs import QUEUE_NAME as discovery_queue

        assert {discovery_queue, audit_queue, briefing_queue} == set(DEFAULT_QUEUES)
