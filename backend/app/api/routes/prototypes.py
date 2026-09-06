"""API HTTP do Prototype Builder (Fase 6).

Nenhum endpoint aqui gera código, executa conteúdo do usuário ou chama IA
— é CRUD validado sobre `Prototype`. Sem autenticação (mesma limitação já
documentada em todas as fases anteriores): todos os protótipos são
visíveis/editáveis por qualquer chamador, já que não há usuário para
isolar (ver `app.domains.prototypes.service`, docstring do módulo).
"""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.session import get_db
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
    components: list[dict]
    settings: dict
    created_at: datetime
    updated_at: datetime


class PrototypeListItemResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
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
    lista de forma divergente do backend."""
    return [
        ComponentTypeResponse(type=t, category=COMPONENT_CATEGORIES.get(t, "layout"))
        for t in sorted(COMPONENT_TYPES)
    ]


@router.post("", response_model=PrototypeResponse, status_code=status.HTTP_201_CREATED)
def create_prototype(payload: PrototypeCreateRequest, db: Session = Depends(get_db)) -> PrototypeResponse:
    service = PrototypeService(db)
    prototype = service.create(name=payload.name, description=payload.description)
    db.commit()
    db.refresh(prototype)
    return _to_response(prototype)


@router.get("", response_model=PrototypeListResponse)
def list_prototypes(
    db: Session = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> PrototypeListResponse:
    service = PrototypeService(db)
    page = service.list(limit=limit, offset=offset)
    return PrototypeListResponse(
        items=[
            PrototypeListItemResponse(
                id=p.id,
                name=p.name,
                description=p.description,
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
def get_prototype(prototype_id: uuid.UUID, db: Session = Depends(get_db)) -> PrototypeResponse:
    service = PrototypeService(db)
    prototype = service.get(prototype_id)
    if prototype is None:
        raise AppError(
            f"Prototype {prototype_id} não encontrado.",
            code="prototype_not_found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return _to_response(prototype)


@router.put("/{prototype_id}", response_model=PrototypeResponse)
def update_prototype(
    prototype_id: uuid.UUID, payload: PrototypeUpdateRequest, db: Session = Depends(get_db)
) -> PrototypeResponse:
    service = PrototypeService(db)
    try:
        prototype = service.update(
            prototype_id,
            name=payload.name,
            description=payload.description,
            components=payload.components,
            settings=payload.settings,
        )
    except LookupError as exc:
        raise AppError(str(exc), code="prototype_not_found", status_code=status.HTTP_404_NOT_FOUND) from exc
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
def delete_prototype(prototype_id: uuid.UUID, db: Session = Depends(get_db)) -> None:
    service = PrototypeService(db)
    deleted = service.delete(prototype_id)
    if not deleted:
        raise AppError(
            f"Prototype {prototype_id} não encontrado.",
            code="prototype_not_found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    db.commit()
