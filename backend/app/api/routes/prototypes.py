"""API HTTP do Prototype Builder (Fase 6; autenticação + vínculo com
Company no Prompt 10).

Toda rota depende de `get_current_user` — não há mais nenhum endpoint
público neste router além do catálogo de tipos (que não expõe dado de
nenhum usuário). Leitura/escrita de um `Prototype` específico sempre passa
por `get_accessible_prototype_or_404`, nunca confia em nada vindo do
payload do cliente para decidir acesso (mesmo padrão do resto do CRM,
Fase 7).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.core.rate_limit import check_and_increment
from app.db.session import get_db
from app.domains.auth.dependencies import get_current_user
from app.domains.auth.models import User
from app.domains.prototypes.authorization import get_accessible_prototype_or_404
from app.domains.prototypes.generation.service import GenerationInProgressError, PrototypeGenerationService
from app.domains.prototypes.jobs import enqueue_or_run_prototype_generation
from app.domains.prototypes.models import GenerationRun, GenerationStatus
from app.domains.prototypes.schemas import (
    COMPONENT_CATEGORIES,
    COMPONENT_TYPES,
    PrototypeCreateRequest,
    PrototypeUpdateRequest,
)
from app.domains.prototypes.service import PrototypeService

router = APIRouter(prefix="/api/prototypes", tags=["prototypes"])


class PrototypeResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    company_id: uuid.UUID | None
    components: list[dict]
    settings: dict
    created_at: datetime
    updated_at: datetime


class PrototypeListItemResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    company_id: uuid.UUID | None
    component_count: int
    created_at: datetime
    updated_at: datetime


class PrototypeListResponse(BaseModel):
    items: list[PrototypeListItemResponse]
    total: int
    limit: int
    offset: int


class ComponentTypeResponse(BaseModel):
    type: str
    category: str


class GenerationRunResponse(BaseModel):
    id: uuid.UUID
    prototype_id: uuid.UUID
    company_id: uuid.UUID
    status: GenerationStatus
    provider: str | None
    model: str | None
    prompt_version: str
    context_version: str
    input_tokens: int | None
    output_tokens: int | None
    duration_ms: float | None
    error_code: str | None
    error_message: str | None
    grounding_warnings: list[str] | None
    created_at: datetime
    completed_at: datetime | None
    execution_mode: str | None = None


def _generation_to_response(run: GenerationRun, *, execution_mode: str | None = None) -> GenerationRunResponse:
    return GenerationRunResponse(
        id=run.id,
        prototype_id=run.prototype_id,
        company_id=run.company_id,
        status=run.status,
        provider=run.provider,
        model=run.model,
        prompt_version=run.prompt_version,
        context_version=run.context_version,
        input_tokens=run.input_tokens,
        output_tokens=run.output_tokens,
        duration_ms=run.duration_ms,
        error_code=run.error_code,
        error_message=run.error_message,
        grounding_warnings=run.grounding_warnings,
        created_at=run.created_at,
        completed_at=run.completed_at,
        execution_mode=execution_mode,
    )


def _to_response(prototype) -> PrototypeResponse:
    return PrototypeResponse(
        id=prototype.id,
        name=prototype.name,
        description=prototype.description,
        company_id=prototype.company_id,
        components=prototype.components,
        settings=prototype.settings,
        created_at=prototype.created_at,
        updated_at=prototype.updated_at,
    )


@router.get("/meta/component-types", response_model=list[ComponentTypeResponse])
def get_component_types() -> list[ComponentTypeResponse]:
    """Catálogo de tipos de componente aceitos — a mesma fonte de verdade
    usada para validar `POST`/`PUT` (`app.domains.prototypes.schemas.
    COMPONENT_TYPES`), exposta para o frontend nunca precisar hardcodar a
    lista de forma divergente do backend. Sem dado de usuário — não exige
    autenticação (mesmo espírito de `GET /api/crm/pipeline/stages`, que
    também é um catálogo estático)."""
    return [
        ComponentTypeResponse(type=t, category=COMPONENT_CATEGORIES.get(t, "layout"))
        for t in sorted(COMPONENT_TYPES)
    ]


@router.post("", response_model=PrototypeResponse, status_code=status.HTTP_201_CREATED)
def create_prototype(
    payload: PrototypeCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PrototypeResponse:
    service = PrototypeService(db)
    try:
        prototype = service.create(
            name=payload.name,
            description=payload.description,
            company_id=payload.company_id,
            user_id=current_user.id,
        )
    except LookupError as exc:
        raise AppError(str(exc), code="company_not_found", status_code=status.HTTP_404_NOT_FOUND) from exc
    except PermissionError as exc:
        # 404, não 403 — mesmo motivo documentado em
        # app.domains.prototypes.authorization: não vazar existência.
        raise AppError(str(exc), code="company_not_found", status_code=status.HTTP_404_NOT_FOUND) from exc

    db.commit()
    db.refresh(prototype)
    return _to_response(prototype)


@router.get("", response_model=PrototypeListResponse)
def list_prototypes(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> PrototypeListResponse:
    service = PrototypeService(db)
    page = service.list_for_user(user_id=current_user.id, limit=limit, offset=offset)
    return PrototypeListResponse(
        items=[
            PrototypeListItemResponse(
                id=p.id,
                name=p.name,
                description=p.description,
                company_id=p.company_id,
                component_count=len(p.components),
                created_at=p.created_at,
                updated_at=p.updated_at,
            )
            for p in page.items
        ],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/{prototype_id}", response_model=PrototypeResponse)
def get_prototype(
    prototype_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PrototypeResponse:
    prototype = get_accessible_prototype_or_404(db, prototype_id, current_user)
    return _to_response(prototype)


@router.put("/{prototype_id}", response_model=PrototypeResponse)
def update_prototype(
    prototype_id: uuid.UUID,
    payload: PrototypeUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PrototypeResponse:
    prototype = get_accessible_prototype_or_404(db, prototype_id, current_user)
    service = PrototypeService(db)
    try:
        prototype = service.update(
            prototype,
            name=payload.name,
            description=payload.description,
            components=payload.components,
            settings=payload.settings,
        )
    except (ValueError, ValidationError) as exc:
        raise AppError(
            f"Árvore de componentes inválida: {exc}",
            code="invalid_component_tree",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        ) from exc

    db.commit()
    db.refresh(prototype)
    return _to_response(prototype)


@router.delete("/{prototype_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_prototype(
    prototype_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    prototype = get_accessible_prototype_or_404(db, prototype_id, current_user)
    PrototypeService(db).delete(prototype)
    db.commit()


@router.post(
    "/{prototype_id}/generate", response_model=GenerationRunResponse, status_code=status.HTTP_202_ACCEPTED
)
def generate_prototype(
    prototype_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> GenerationRunResponse:
    """Dispara a geração por IA da árvore de componentes (Fase 9 /
    Prompt 11). Mesma autorização de qualquer outra rota de `Prototype`
    (só quem tem `Opportunity` para a empresa). Rate limit por
    `prototype_id` (seção 6 do Prompt 11 — nunca por usuário/empresa aqui,
    porque o limite é especificamente "evitar um loop de regeneração
    acidental NESTE protótipo"), política `fail_closed` (mesmo motivo de
    Sales Brief/Outreach: custo financeiro direto)."""
    prototype = get_accessible_prototype_or_404(db, prototype_id, current_user)

    allowed = check_and_increment(
        f"ratelimit:prototype_generation:{prototype_id}:{datetime.now(timezone.utc).date().isoformat()}",
        max_attempts=settings.prototype_generation_rate_limit_max_per_day,
        window_seconds=24 * 60 * 60,
        on_unavailable="fail_closed",
    )
    if not allowed:
        raise AppError(
            "Limite diário de gerações atingido para este protótipo.",
            code="prototype_generation_rate_limited",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        )

    service = PrototypeGenerationService(db)
    try:
        run = service.start(prototype)
    except GenerationInProgressError as exc:
        raise AppError(str(exc), code="generation_in_progress", status_code=status.HTTP_409_CONFLICT) from exc

    execution_mode = enqueue_or_run_prototype_generation(run.id, db=db)
    db.commit()
    db.refresh(run)

    return _generation_to_response(run, execution_mode=execution_mode)


@router.get("/{prototype_id}/generations/{generation_id}", response_model=GenerationRunResponse)
def get_generation(
    prototype_id: uuid.UUID,
    generation_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> GenerationRunResponse:
    get_accessible_prototype_or_404(db, prototype_id, current_user)

    run = PrototypeGenerationService(db).get(prototype_id, generation_id)
    if run is None:
        raise AppError(
            f"Geração {generation_id} não encontrada para o protótipo {prototype_id}.",
            code="generation_not_found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return _generation_to_response(run)
