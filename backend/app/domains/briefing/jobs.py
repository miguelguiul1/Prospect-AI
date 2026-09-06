"""Integração do Sales Brief com a abstração de jobs da Fase 0.

Mesmo padrão de `app.domains.discovery.jobs`/`app.domains.audit.jobs`:
`enqueue_or_run_sales_brief` tenta enfileirar no RQ; se a fila estiver
indisponível, executa de forma síncrona. Faz sentido enfileirar o Sales
Brief especificamente porque, ao contrário do Opportunity Score, ele chama
uma API externa (Anthropic) e pode ser lento — o mesmo motivo que já levou
Discovery e Digital Audit a seguir este padrão.
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.session import SessionLocal
from app.jobs.base import Job, JobContext
from app.jobs.queue import get_queue

logger = get_logger(__name__)


class SalesBriefJob(Job):
    name = "briefing.generate_sales_brief"
    max_retries = 0  # o provider de IA nunca é retentado automaticamente (ver providers/errors.py).

    def run(self, context: JobContext, **kwargs: Any) -> None:
        company_id = kwargs["company_id"]
        run_sales_brief(company_id)


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
        queue = get_queue("briefing")
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
