"""Conexão com a fila (Redis + RQ) usada pelo processamento assíncrono.

Discovery, Digital Audit e Sales Brief enfileiram jobs reais desde as
Fases 1/3/4 (`enqueue_or_run_*` em cada `app/domains/*/jobs.py`); um worker
real (`app.worker`) consome essas filas desde a Fase 8.2.
"""
from __future__ import annotations

from functools import lru_cache

import redis
from rq import Queue, get_current_job

from app.core.config import get_settings
from app.core.logging import bind_request_context


@lru_cache
def get_redis_connection() -> redis.Redis:
    """Cliente Redis com timeout de socket curto e explícito.

    Sem isso, uma tentativa de conexão a um Redis indisponível pode levar
    vários segundos para falhar (observado nesta própria máquina de
    desenvolvimento, que não tem Redis instalado) — inaceitável para um
    cache best-effort (app.domains.discovery.cache) ou para o
    health check, que precisam falhar rápido, não travar a requisição.
    """
    settings = get_settings()
    return redis.from_url(settings.redis_url, socket_connect_timeout=0.2, socket_timeout=0.2)


def get_queue(name: str = "default") -> Queue:
    return Queue(name, connection=get_redis_connection())


def bind_job_context() -> None:
    """Associa `job_id` (e `queue_name`) a todo log emitido durante a
    execução de um job (Fase 8.6 — achado F8.0: nenhum job tinha
    correlação de log até aqui). Chamado no início de cada `run_*` de
    `app/domains/*/jobs.py`.

    Sem efeito quando chamado FORA de um worker real (o caso do fallback
    síncrono, `enqueue_or_run_*` executando na própria requisição HTTP) —
    `get_current_job()` retorna `None` nesse caso, e o `request_id` já
    vinculado pelo `RequestContextMiddleware` continua sendo a correlação
    válida.
    """
    job = get_current_job()
    if job is not None:
        bind_request_context(job_id=job.id, queue_name=job.origin)
