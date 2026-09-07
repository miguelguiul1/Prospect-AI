"""Integração do Sales Brief com a fila RQ (Fase 0, worker real Fase 8).

Mesmo padrão de `app.domains.discovery.jobs`/`app.domains.audit.jobs`:
`enqueue_or_run_sales_brief` tenta enfileirar no RQ; se a fila estiver
indisponível, executa de forma síncrona. Faz sentido enfileirar o Sales
Brief especificamente porque, ao contrário do Opportunity Score, ele chama
uma API externa (Anthropic) e pode ser lento — o mesmo motivo que já levou
Discovery e Digital Audit a seguir este padrão.

Sem retry automático: o provider de IA nunca é retentado automaticamente
(ver providers/errors.py) — um retry de job inteiro poderia gerar uma
segunda chamada paga à Anthropic para o mesmo pedido sem necessidade.
"""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.session import SessionLocal
from app.jobs.queue import get_queue

logger = get_logger(__name__)

# Nome da fila lido por `app.worker` (Fase 8.2).
QUEUE_NAME = "briefing"


def run_sales_brief(company_id: str) -> None:
    """Corpo do job para execução em um processo separado (worker do RQ):
    abre sua própria sessão. Importável isoladamente por referência de
    módulo, como o RQ exige para serializar o job."""
    from app.domains.briefing.service import SalesBriefService  # import tardio: evita ciclo

    db = SessionLocal()
    try:
        service = SalesBriefService(db)
        service.generate(uuid.UUID(company_id))
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def enqueue_or_run_sales_brief(company_id: uuid.UUID, *, db: Session | None = None) -> str:
    """Retorna `"queued"` quando o job foi enfileirado no Redis, ou
    `"executed_sync"` quando rodou no processo atual por fallback.

    Passe `db` quando chamado a partir de um handler HTTP que já tem uma
    sessão aberta — evita abrir uma segunda conexão que não enxergaria dados
    ainda não commitados na primeira (mesmo motivo de `app.domains.audit.jobs`).
    """
    try:
        queue = get_queue(QUEUE_NAME)
        queue.enqueue(run_sales_brief, str(company_id))
        return "queued"
    except Exception as exc:  # noqa: BLE001 - fila indisponível é um modo operacional válido aqui
        logger.warning(
            "sales_brief_queue_unavailable_running_sync",
            company_id=str(company_id),
            error_type=exc.__class__.__name__,
        )
        if db is not None:
            from app.domains.briefing.service import SalesBriefService

            SalesBriefService(db).generate(company_id)
        else:
            run_sales_brief(str(company_id))
        return "executed_sync"
