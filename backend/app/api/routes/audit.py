"""API HTTP mínima do Digital Audit.

`POST /api/audit/{company_id}` cria e executa uma auditoria (enfileirada,
ou de forma síncrona se a fila estiver indisponível — mesmo padrão de
`app.domains.discovery.jobs`). `GET /api/audit/{company_id}` consulta a
auditoria mais recente da empresa.

Nenhuma operação destrutiva/administrativa é exposta aqui — o sistema
ainda não tem autenticação (mesma limitação já documentada nas Fases 1/2).
"""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.session import get_db
from app.domains.audit.enums import AuditStatus
from app.domains.audit.jobs import enqueue_or_run_audit
from app.domains.audit.models import AuditSnapshot, WebsiteQuality
from app.domains.audit.service import DigitalAuditService
from app.domains.evidence.enums import ConfidenceLevel, DataState

router = APIRouter(prefix="/api/audit", tags=["audit"])


class WebsiteQualityResponse(BaseModel):
    score: float | None
    components: dict | None
    confidence: ConfidenceLevel | None
    limitations: list | None
    signals: dict | None


class AuditSnapshotResponse(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    run_id: uuid.UUID
    status: AuditStatus
    site_state: DataState | None
    website_url: str | None
    error_code: str | None
    error_message: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    website_quality: WebsiteQualityResponse | None
    execution_mode: str | None = None


def _to_response(snapshot: AuditSnapshot, *, execution_mode: str | None = None) -> AuditSnapshotResponse:
    quality: WebsiteQuality | None = snapshot.website_quality
    return AuditSnapshotResponse(
        id=snapshot.id,
        company_id=snapshot.company_id,
        run_id=snapshot.run_id,
        status=snapshot.status,
        site_state=snapshot.site_state,
        website_url=snapshot.website_url,
        error_code=snapshot.error_code,
        error_message=snapshot.error_message,
        started_at=snapshot.started_at,
        finished_at=snapshot.finished_at,
        created_at=snapshot.created_at,
        website_quality=(
            WebsiteQualityResponse(
                score=quality.score,
                components=quality.components,
                confidence=quality.confidence,
                limitations=quality.limitations,
                signals=quality.signals,
            )
            if quality is not None
            else None
        ),
        execution_mode=execution_mode,
    )


@router.post("/{company_id}", response_model=AuditSnapshotResponse, status_code=status.HTTP_202_ACCEPTED)
def create_audit(company_id: uuid.UUID, db: Session = Depends(get_db)) -> AuditSnapshotResponse:
    service = DigitalAuditService(db)
    try:
        snapshot = service.start_audit(company_id)
    except ValueError as exc:
        raise AppError(str(exc), code="company_not_found", status_code=status.HTTP_404_NOT_FOUND) from exc
    db.commit()

    execution_mode = enqueue_or_run_audit(snapshot.id, db=db)
    db.commit()

    db.refresh(snapshot)
    return _to_response(snapshot, execution_mode=execution_mode)


@router.get("/{company_id}", response_model=AuditSnapshotResponse)
def get_latest_audit(company_id: uuid.UUID, db: Session = Depends(get_db)) -> AuditSnapshotResponse:
    snapshot = (
        db.query(AuditSnapshot)
        .filter(AuditSnapshot.company_id == company_id)
        .order_by(AuditSnapshot.created_at.desc())
        .first()
    )
    if snapshot is None:
        raise AppError(
            f"Nenhuma auditoria encontrada para a empresa {company_id}.",
            code="audit_not_found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return _to_response(snapshot)
