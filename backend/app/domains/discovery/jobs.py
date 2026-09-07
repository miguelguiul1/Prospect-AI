"""Integração do Discovery com a fila RQ (Fase 0, worker real Fase 8).

`enqueue_or_run_discovery` tenta enfileirar no RQ (Redis); se a fila não
estiver acessível — como em toda máquina de desenvolvimento usada neste
projeto até aqui, que não tem Redis instalado (ver docs/development.md) —
executa a mesma lógica de forma síncrona, em vez de travar ou derrubar a
requisição. Isso é um modo de execução documentado, não uma substituição do
Redis pela arquitetura: em produção, com Redis E um worker real (`app.worker`,
Fase 8.2) disponíveis, o caminho enfileirado é sempre o usado.

Duas formas de rodar a busca síncrona:

- Com uma sessão já aberta (`db=...`, o caso do endpoint HTTP): reaproveita
  exatamente essa sessão/conexão, para não divergir do que a requisição já
  viu ou gravou na mesma transação.
- Sem sessão (`db=None`, o caso do worker real do RQ, que roda em outro
  processo): abre sua própria sessão via `SessionLocal`.

Sem retry automático: retries de rede já acontecem dentro do provider
(Fase 1); um retry de job inteiro poderia duplicar chamadas pagas à API de
descoberta sem necessidade.
"""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.session import SessionLocal
from app.jobs.queue import get_queue

logger = get_logger(__name__)

# Nome da fila lido por `app.worker` (Fase 8.2).
QUEUE_NAME = "discovery"


def run_discovery_search(search_run_id: str) -> None:
    """Corpo do job para execução em um processo separado (worker do RQ):
    abre sua própria sessão. Importável isoladamente por referência de
    módulo, como o RQ exige para serializar o job."""
    from app.domains.discovery.service import DiscoveryService  # import tardio: evita ciclo com providers

    db = SessionLocal()
    try:
        service = DiscoveryService(db)
        service.execute(uuid.UUID(search_run_id))
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def enqueue_or_run_discovery(search_run_id: uuid.UUID, *, db: Session | None = None) -> str:
    """Retorna `"queued"` quando o job foi enfileirado no Redis, ou
    `"executed_sync"` quando rodou no processo atual por fallback.

    Passe `db` quando chamado a partir de um handler HTTP que já tem uma
    sessão aberta para este `SearchRun` — evita abrir uma segunda conexão
    que não enxergaria dados ainda não commitados na primeira.
    """
    try:
        queue = get_queue(QUEUE_NAME)
        queue.enqueue(run_discovery_search, str(search_run_id))
        return "queued"
    except Exception as exc:  # noqa: BLE001 - fila indisponível é um modo operacional válido aqui
        logger.warning(
            "discovery_queue_unavailable_running_sync",
            search_run_id=str(search_run_id),
            error_type=exc.__class__.__name__,
        )
        if db is not None:
            from app.domains.discovery.service import DiscoveryService

            DiscoveryService(db).execute(search_run_id)
        else:
            run_discovery_search(str(search_run_id))
        return "executed_sync"
