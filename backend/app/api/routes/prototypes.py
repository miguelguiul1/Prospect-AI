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
from datetime import datetime

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.session import get_db
from app.domains.auth.dependencies import get_current_user
from app.domains.auth.models import User
from app.domains.prototypes.authorization import get_accessible_prototype_or_404
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
