"""Logging estruturado com suporte a IDs de correlação.

A arquitetura v0.2 (seção 20 — Observabilidade) exige que qualquer execução
futura (requisição HTTP, job de Discovery, execução de auditoria) possa ser
correlacionada por request_id/job_id/run_id nos logs. Esta fase estabelece
o formato e as funções de contexto; nenhum job real ainda os popula, já que
Discovery/Audit/Scoring são de fases futuras.

Nenhum serviço externo de observabilidade (Sentry, etc.) é integrado aqui —
os logs saem estruturados (JSON em produção, legível em desenvolvimento)
para stdout, prontos para serem coletados por qualquer ferramenta futura.
"""
from __future__ import annotations

import logging
import sys

import structlog


def configure_logging(log_level: str = "INFO", json_logs: bool = True) -> None:
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=log_level)

    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    renderer = structlog.processors.JSONRenderer() if json_logs else structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, log_level.upper(), logging.INFO)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.BoundLogger:
    return structlog.get_logger(name)


def bind_request_context(**kwargs: str) -> None:
    """Associa IDs de correlação (request_id, job_id, run_id, ...) a todo log
    emitido no contexto atual, até `clear_request_context()` ser chamado."""
    structlog.contextvars.bind_contextvars(**kwargs)


def clear_request_context() -> None:
    structlog.contextvars.clear_contextvars()
