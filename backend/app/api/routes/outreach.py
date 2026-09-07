"""API HTTP do Assisted Outreach (Fase 7).

Geração de rascunho é limitada por rate limiting (Prompt 11, seção 20.1:
"IA" é uma das prioridades) — best-effort via Redis, mesmo padrão do login
(`app.core.rate_limit`). Autorização sempre derivada da `Opportunity` dona
do outreach (nunca um `owner_id` próprio em `Outreach`).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.core.rate_limit import check_and_increment
from app.db.session import get_db
from app.domains.auth.dependencies import get_current_user
from app.domains.auth.models import User
from app.domains.crm.authorization import get_owned_opportunity_or_404
from app.domains.crm.models import Contact
from app.domains.outreach.enums import OutreachChannel, OutreachStatus
from app.domains.outreach.models import Outreach
from app.domains.outreach.schemas import GenerateOutreachRequest, OutreachEditRequest, OutreachTransitionRequest
from app.domains.outreach.service import OutreachGenerationError, OutreachService

router = APIRouter(prefix="/api/crm", tags=["outreach"])


class OutreachResponse(BaseModel):
    id: uuid.UUID
    opportunity_id: uuid.UUID
    contact_id: uuid.UUID | None
    channel: OutreachChannel
    status: OutreachStatus
    subject: str | None
    message: str | None
    rationale: str | None
    evidence_ids: list[str]
    generated_by_ai: bool
    created_at: datetime
    updated_at: datetime


def _to_response(outreach: Outreach) -> OutreachResponse:
    return OutreachResponse(
        id=outreach.id,
        opportunity_id=outreach.opportunity_id,
        contact_id=outreach.contact_id,
        channel=outreach.channel,
        status=outreach.status,
        subject=outreach.subject,
        message=outreach.message,
        rationale=outreach.rationale,
        evidence_ids=outreach.evidence_ids or [],
        generated_by_ai=outreach.generated_by_ai,
        created_at=outreach.created_at,
        updated_at=outreach.updated_at,
    )


def _get_owned_outreach_or_404(db: Session, outreach_id: uuid.UUID, user: User) -> Outreach:
    outreach = db.get(Outreach, outreach_id)
    if outreach is None:
        raise AppError(f"Outreach {outreach_id} não encontrado.", code="outreach_not_found", status_code=status.HTTP_404_NOT_FOUND)
    get_owned_opportunity_or_404(db, outreach.opportunity_id, user)
    return outreach


@router.post(
    "/opportunities/{opportunity_id}/outreach/generate",
    response_model=OutreachResponse,
    status_code=status.HTTP_201_CREATED,
)
def generate_outreach(
    opportunity_id: uuid.UUID,
    payload: GenerateOutreachRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> OutreachResponse:
    opportunity = get_owned_opportunity_or_404(db, opportunity_id, current_user)

    allowed = check_and_increment(
        f"ratelimit:outreach:{current_user.id}:{datetime.now(timezone.utc).date().isoformat()}",
        max_attempts=settings.outreach_rate_limit_max_per_day,
        window_seconds=24 * 60 * 60,
    )
    if not allowed:
        raise AppError(
            "Limite diário de gerações de outreach atingido.",
            code="outreach_rate_limited",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        )

    contact: Contact | None = None
    if payload.contact_id is not None:
        contact = db.get(Contact, payload.contact_id)
        if contact is None or contact.company_id != opportunity.company_id:
            raise AppError(
                "Contato inválido para esta oportunidade.",
                code="invalid_contact",
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            )

    service = OutreachService(db)
    try:
        outreach = service.generate_draft(
            opportunity, contact=contact, channel=payload.channel, user_id=current_user.id
        )
    except OutreachGenerationError as exc:
        db.rollback()
        raise AppError(
            f"Não foi possível gerar a sugestão de outreach: {exc}",
            code="outreach_generation_failed",
            status_code=status.HTTP_502_BAD_GATEWAY,
        ) from exc

    db.commit()
    db.refresh(outreach)
    return _to_response(outreach)


@router.get("/opportunities/{opportunity_id}/outreach", response_model=list[OutreachResponse])
def list_outreach(
    opportunity_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> list[OutreachResponse]:
    get_owned_opportunity_or_404(db, opportunity_id, current_user)
    items = OutreachService(db).list_for_opportunity(opportunity_id)
    return [_to_response(o) for o in items]


@router.patch("/outreach/{outreach_id}", response_model=OutreachResponse)
def edit_outreach(
    outreach_id: uuid.UUID,
    payload: OutreachEditRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> OutreachResponse:
    outreach = _get_owned_outreach_or_404(db, outreach_id, current_user)
    try:
        OutreachService(db).edit(outreach, subject=payload.subject, message=payload.message)
    except ValueError as exc:
        raise AppError(str(exc), code="outreach_not_editable", status_code=status.HTTP_409_CONFLICT) from exc
    db.commit()
    db.refresh(outreach)
    return _to_response(outreach)


@router.post("/outreach/{outreach_id}/transition", response_model=OutreachResponse)
def transition_outreach(
    outreach_id: uuid.UUID,
    payload: OutreachTransitionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> OutreachResponse:
    outreach = _get_owned_outreach_or_404(db, outreach_id, current_user)
    try:
        OutreachService(db).transition(outreach, action=payload.action, user_id=current_user.id)
    except ValueError as exc:
        raise AppError(str(exc), code="invalid_outreach_transition", status_code=status.HTTP_409_CONFLICT) from exc
    db.commit()
    db.refresh(outreach)
    return _to_response(outreach)
