"""Integração do Digital Audit com a abstração de jobs da Fase 0.

Mesmo padrão de `app.domains.discovery.jobs` (Fase 1): `enqueue_or_run_audit`
tenta enfileirar no RQ; se a fila estiver indisponível, executa de forma
síncrona — com a sessão já aberta pela requisição HTTP quando fornecida, ou
abrindo uma própria (caso de um worker real do RQ, em outro processo).
Redis continua sendo a arquitetura oficial; isto é só um fallback
operacional documentado, não uma substituição.
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


class DigitalAuditJob(Job):
    name = "audit.run_digital_audit"
    max_retries = 0  # retries de rede já acontecem dentro de fetch_safely.

    def run(self, context: JobContext, **kwargs: Any) -> None:
        audit_snapshot_id = kwargs["audit_snapshot_id"]
        run_digital_audit(audit_snapshot_id)


def run_digital_audit(audit_snapshot_id: str) -> None:
    """Corpo do job para execução em um processo separado (worker do RQ):
    abre sua própria sessão. Importável isoladamente por referência de
    módulo, como o RQ exige para serializar o job."""
    from app.domains.audit.service import DigitalAuditService  # import tardio: evita ciclo

    db = SessionLocal()
    try:
        service = DigitalAuditService(db)
        service.execute(uuid.UUID(audit_snapshot_id))
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def enqueue_or_run_audit(audit_snapshot_id: uuid.UUID, *, db: Session | None = None) -> str:
    """Retorna `"queued"` quando o job foi enfileirado no Redis, ou
    `"executed_sync"` quando rodou no processo atual por fallback.

    Passe `db` quando chamado a partir de um handler HTTP que já tem uma
    sessão aberta para este `AuditSnapshot` — evita abrir uma segunda
    conexão que não enxergaria dados ainda não commitados na primeira.
    """
    try:
        queue = get_queue("audit")
        queue.enqueue(run_digital_audit, str(audit_snapshot_id))
        return "queued"
    except Exception as exc:  # noqa: BLE001 - fila indisponível é um modo operacional válido aqui
        logger.warning(
            "audit_queue_unavailable_running_sync",
            audit_snapshot_id=str(audit_snapshot_id),
            error_type=exc.__class__.__name__,
        )
        if db is not None:
            from app.domains.audit.service import DigitalAuditService

            DigitalAuditService(db).execute(audit_snapshot_id)
        else:
            run_digital_audit(str(audit_snapshot_id))
        return "executed_sync"
