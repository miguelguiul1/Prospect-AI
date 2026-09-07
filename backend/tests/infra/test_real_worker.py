"""Validação do worker RQ (Fase 8.2) contra Redis REAL — não `fakeredis`
(ver `tests/jobs/test_worker_integration.py`, que é explicitamente MOCK).

Fecha a lacuna deixada pela Fase 8.2: o mecanismo enqueue→worker→execução
foi provado com `fakeredis`, mas nunca contra um Redis de verdade. Mesma
regra dos outros arquivos deste diretório: pulado com motivo explícito se
`REAL_REDIS_URL` não conectar; nunca finge sucesso.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
import redis as redis_lib
from rq import Queue, SimpleWorker
from rq.job import JobStatus

REAL_REDIS_URL = os.environ.get("REAL_REDIS_URL", "redis://localhost:6379/0")

# `tests/jobs/_fixtures.py` — reaproveitado aqui (mesma função importável
# por caminho de módulo que RQ exige) em vez de duplicar um fixture igual.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "jobs"))


def _redis_available() -> bool:
    try:
        conn = redis_lib.from_url(REAL_REDIS_URL, socket_connect_timeout=0.5, socket_timeout=0.5)
        return bool(conn.ping())
    except Exception:  # noqa: BLE001
        return False


pytestmark = pytest.mark.skipif(
    not _redis_available(),
    reason="Redis real indisponível — ver test_real_redis.py para o motivo completo.",
)


@pytest.fixture()
def real_redis_connection():
    conn = redis_lib.from_url(REAL_REDIS_URL, socket_connect_timeout=0.5, socket_timeout=0.5)
    yield conn
    for key in conn.scan_iter(match="rq:*test_real_worker*"):
        conn.delete(key)


class TestWorkerAgainstRealRedis:
    def test_a_job_enqueued_to_real_redis_is_actually_executed(self, real_redis_connection) -> None:
        import _fixtures

        queue = Queue("test_real_worker_q", connection=real_redis_connection)
        job = queue.enqueue(_fixtures.add, 10, 20)
        assert job.get_status() == JobStatus.QUEUED

        worker = SimpleWorker(["test_real_worker_q"], connection=real_redis_connection)
        worker.work(burst=True)

        job.refresh()
        assert job.get_status() == JobStatus.FINISHED
        assert job.return_value() == 30

        queue.delete(delete_jobs=True)
