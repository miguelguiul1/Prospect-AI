"""API HTTP mínima do Sales Brief.

`POST /api/sales-brief/{company_id}` valida as precondições de forma
síncrona (empresa existe, Opportunity Score já calculado — erros viram
404/409 imediatos, nunca um job enfileirado que falharia silenciosamente
depois) e então gera o briefing (enfileirado, ou de forma síncrona se a fila
estiver indisponível — mesmo padrão de `app.domains.audit`/`discovery`).
`GET /api/sales-brief/{company_id}` consulta o briefing mais recente.

Uma falha do provider de IA (indisponível, timeout, resposta inválida)
NUNCA vira um HTTP 500 nem um briefing inventado — o response volta com
`status="failed"` e o motivo em `error_code`/`error_message`, sempre com
HTTP 202 (a requisição foi aceita e processada; o resultado é que não foi
possível gerar o conteúdo).

Rate limiting (Fase 8.3 — achado R11 da auditoria F8.0: esta era a única
operação de custo de IA do projeto sem nenhum limite). Esta rota é anterior
à autenticação (Fase 4, antes da Fase 7) e nunca foi retrofitada com auth —
por isso o limite é por `company_id`, não por usuário, com política
`fail_closed`: se o Redis (mecanismo de controle) estiver fora do ar,
BLOQUEIA a geração em vez de permitir chamadas ilimitadas à Anthropic.
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
from app.domains.briefing.jobs import enqueue_or_run_sales_brief
from app.domains.briefing.models import SalesBrief, SalesBriefStatus
from app.domains.briefing.service import SalesBriefService

router = APIRouter(prefix="/api/sales-brief", tags=["sales-brief"])


class SalesBriefResponse(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    opportunity_score_id: uuid.UUID
    status: SalesBriefStatus
    content: dict | None
    provider: str | None
    model: str | None
    prompt_version: str
    error_code: str | None
    error_message: str | None
    duration_ms: float | None
    input_tokens: int | None
    output_tokens: int | None
    generated_at: datetime
    created_at: datetime
    execution_mode: str | None = None


def _to_response(brief: SalesBrief, *, execution_mode: str | None = None) -> SalesBriefResponse:
    return SalesBriefResponse(
        id=brief.id,
        company_id=brief.company_id,
        opportunity_score_id=brief.opportunity_score_id,
        status=brief.status,
        content=brief.content,
        provider=brief.provider,
        model=brief.model,
        prompt_version=brief.prompt_version,
        error_code=brief.error_code,
        error_message=brief.error_message,
        duration_ms=brief.duration_ms,
        input_tokens=brief.input_tokens,
        output_tokens=brief.output_tokens,
        generated_at=brief.generated_at,
        created_at=brief.created_at,
        execution_mode=execution_mode,
    )


@router.post("/{company_id}", response_model=SalesBriefResponse, status_code=status.HTTP_202_ACCEPTED)
def create_sales_brief(
    company_id: uuid.UUID,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> SalesBriefResponse:
    allowed = check_and_increment(
        f"ratelimit:sales_brief:{company_id}:{datetime.now(timezone.utc).date().isoformat()}",
        max_attempts=settings.sales_brief_rate_limit_max_per_day,
        window_seconds=24 * 60 * 60,
        on_unavailable="fail_closed",
    )
    if not allowed:
        raise AppError(
            "Limite diário de gerações de Sales Brief atingido para esta empresa.",
            code="rate_limited",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        )

    service = SalesBriefService(db)
    try:
        service.validate_preconditions(company_id)
    except LookupError as exc:
        raise AppError(str(exc), code="company_not_found", status_code=status.HTTP_404_NOT_FOUND) from exc
    except ValueError as exc:
        raise AppError(str(exc), code="opportunity_score_required", status_code=status.HTTP_409_CONFLICT) from exc

    execution_mode = enqueue_or_run_sales_brief(company_id, db=db)
    db.commit()

    brief = service.get_latest(company_id)
    assert brief is not None  # gerado (com sucesso ou falha) por enqueue_or_run_sales_brief acima
    return _to_response(brief, execution_mode=execution_mode)


@router.get("/{company_id}", response_model=SalesBriefResponse)
def get_latest_sales_brief(company_id: uuid.UUID, db: Session = Depends(get_db)) -> SalesBriefResponse:
    service = SalesBriefService(db)
    brief = service.get_latest(company_id)
    if brief is None:
        raise AppError(
            f"Nenhum Sales Brief encontrado para a empresa {company_id}.",
            code="sales_brief_not_found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return _to_response(brief)
