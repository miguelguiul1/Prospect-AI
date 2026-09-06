"""API HTTP mínima do Opportunity Score.

`POST /api/scoring/{company_id}` calcula (ou recalcula) o score da auditoria
mais recente da empresa — sempre síncrono, porque o cálculo é determinístico,
puramente local (não chama nenhum provider externo) e rápido, ao contrário
de Discovery/Digital Audit (que por isso usam o padrão enqueue_or_run). `GET
/api/scoring/{company_id}` consulta o score mais recente.

Nenhuma operação destrutiva/administrativa é exposta aqui — mesma limitação
de autenticação já documentada nas Fases 1-3.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.session import get_db
from app.domains.evidence.enums import ConfidenceLevel
from app.domains.scoring.models import OpportunityScore, OpportunityTier
from app.domains.scoring.service import OpportunityScoringService

router = APIRouter(prefix="/api/scoring", tags=["scoring"])


class OpportunityScoreResponse(BaseModel):
    id: uuid.UUID
    audit_snapshot_id: uuid.UUID
    score: float | None
    tier: OpportunityTier | None
    confidence: ConfidenceLevel | None
    scoring_version: str
    breakdown: dict | None
    recommended_product: str | None
    created_at: datetime
    updated_at: datetime


def _to_response(score: OpportunityScore) -> OpportunityScoreResponse:
    return OpportunityScoreResponse(
        id=score.id,
        audit_snapshot_id=score.audit_snapshot_id,
        score=score.score,
        tier=score.tier,
        confidence=score.confidence,
        scoring_version=score.scoring_version,
        breakdown=score.breakdown,
        recommended_product=score.recommended_product,
        created_at=score.created_at,
        updated_at=score.updated_at,
    )


@router.post("/{company_id}", response_model=OpportunityScoreResponse)
def compute_score(company_id: uuid.UUID, db: Session = Depends(get_db)) -> OpportunityScoreResponse:
    service = OpportunityScoringService(db)
    try:
        score = service.compute(company_id)
    except LookupError as exc:
        raise AppError(str(exc), code="company_not_found", status_code=status.HTTP_404_NOT_FOUND) from exc
    except ValueError as exc:
        raise AppError(str(exc), code="opportunity_score_precondition_failed", status_code=status.HTTP_409_CONFLICT) from exc
    db.commit()
    db.refresh(score)
    return _to_response(score)


@router.get("/{company_id}", response_model=OpportunityScoreResponse)
def get_latest_score(company_id: uuid.UUID, db: Session = Depends(get_db)) -> OpportunityScoreResponse:
    service = OpportunityScoringService(db)
    score = service.get_latest(company_id)
    if score is None:
        raise AppError(
            f"Nenhum Opportunity Score encontrado para a empresa {company_id}.",
            code="opportunity_score_not_found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return _to_response(score)
