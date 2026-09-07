"""Entrypoint do worker RQ real (Fase 8.2).

Antes desta fase, nenhum processo consumia as filas Redis (`discovery`,
`audit`, `briefing`) — mesmo com Redis disponível, um job "enfileirado"
ficaria parado para sempre, porque nenhum worker jamais existiu no projeto
(achado da auditoria F8.0, seção 10). Este módulo é o processo que resolve
isso.

Uso:
    python -m app.worker                    # as três filas reais do projeto
    python -m app.worker discovery audit     # subconjunto específico

Não retenta jobs automaticamente por padrão — cada domínio já decidiu
deliberadamente não reexecutar (retries de rede já acontecem dentro do
provider/`fetch_safely`; um retry de job inteiro poderia duplicar uma
chamada paga à Anthropic/Google, ver os comentários em cada
`app/domains/*/jobs.py`). Se algum job precisar de retry no futuro, isso
deve ser configurado explicitamente em `queue.enqueue(..., retry=Retry(...))`
no ponto de enfileiramento, não neste worker.

Shutdown gracioso: o `Worker.work()` da própria biblioteca RQ já trata
SIGINT/SIGTERM nativamente — um primeiro sinal (Ctrl+C) pede para o job
atual terminar antes de sair (warm shutdown); um segundo sinal força saída
imediata (cold shutdown). Nenhum tratamento de sinal próprio é adicionado
aqui, para não sobrescrever esse comportamento já correto da biblioteca.
"""
from __future__ import annotations

import sys

from rq import Worker

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.jobs.queue import get_redis_connection

# Sincronizado manualmente com `QUEUE_NAME` em cada
# `app/domains/{discovery,audit,briefing,prototypes}/jobs.py` — são as
# quatro únicas filas reais do projeto (confirmado por busca em toda a
# auditoria F8.0; Assisted Outreach, Fase 7, é deliberadamente síncrono e
# não usa fila). `prototype_generation` adicionada na Fase 9 / Prompt 11.
# Se uma fila nova for criada, precisa ser adicionada aqui também, ou o
# worker nunca vai consumi-la.
DEFAULT_QUEUES = ["discovery", "audit", "briefing", "prototype_generation"]

logger = get_logger(__name__)


def main(queue_names: list[str] | None = None) -> None:
    settings = get_settings()
    configure_logging(log_level=settings.log_level, json_logs=settings.is_production)

    queues = queue_names or DEFAULT_QUEUES
    connection = get_redis_connection()

    logger.info("worker_starting", queues=queues, app_env=settings.app_env)

    worker = Worker(queues, connection=connection)
    worker.work(with_scheduler=False)


if __name__ == "__main__":
    main(sys.argv[1:] or None)
