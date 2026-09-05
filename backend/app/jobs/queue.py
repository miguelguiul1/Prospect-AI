"""Conexão com a fila (Redis + RQ) usada pelo processamento assíncrono futuro.

Fase 0 só estabelece a conexão e a fábrica de filas — nenhuma tarefa
(Discovery/Audit/Score/Briefing) é enfileirada ainda.
"""
from __future__ import annotations

from functools import lru_cache

import redis
from rq import Queue

from app.core.config import get_settings


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
