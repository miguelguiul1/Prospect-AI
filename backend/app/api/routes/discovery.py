"""API HTTP mínima do Discovery.

`POST /api/discovery/search` valida a entrada, cria o `SearchRun` e tenta
executá-lo (enfileirado, ou de forma síncrona se a fila estiver
indisponível — ver `app.domains.discovery.jobs`). `GET
/api/discovery/runs/{run_id}` consulta o estado de uma execução.

Nenhuma interface gráfica é criada aqui — apenas os dois endpoints pedidos
pela Fase 1.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.session import get_db
from app.domains.discovery.jobs import enqueue_or_run_discovery
from app.domains.discovery.models import SearchRun, SearchRunStatus
from app.domains.discovery.schemas import DiscoveryQuery
from app.domains.discovery.service import DiscoveryService

router = APIRouter(prefix="/api/discovery", tags=["discovery"])


class SearchRunResponse(BaseModel):
    id: uuid.UUID
    status: SearchRunStatus
    provider: str
    parameters: dict
    raw_result_count: int | None
    normalized_result_count: int | None
    persisted_count: int | None
    new_company_count: int | None
    pages_fetched: int | None
    error_code: str | None
    error_message: str | None
    cost_estimate: float | None
    cost_currency: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    execution_mode: str | None = None


def _to_response(search_run: SearchRun, *, execution_mode: str | None = None) -> SearchRunResponse:
    return SearchRunResponse(
        id=search_run.id,
        status=search_run.status,
        provider=search_run.provider,
        parameters=search_run.parameters,
        raw_result_count=search_run.raw_result_count,
        normalized_result_count=search_run.normalized_result_count,
        persisted_count=search_run.persisted_count,
        new_company_count=search_run.new_company_count,
        pages_fetched=search_run.pages_fetched,
        error_code=search_run.error_code,
        error_message=search_run.error_message,
        cost_estimate=search_run.cost_estimate,
        cost_currency=search_run.cost_currency,
        started_at=search_run.started_at,
        finished_at=search_run.finished_at,
        created_at=search_run.created_at,
        execution_mode=execution_mode,
    )


@router.post("/search", response_model=SearchRunResponse, status_code=status.HTTP_202_ACCEPTED)
def create_discovery_search(payload: DiscoveryQuery, db: Session = Depends(get_db)) -> SearchRunResponse:
    service = DiscoveryService(db)
    search_run = service.start_run(payload)
    db.commit()

    execution_mode = enqueue_or_run_discovery(search_run.id, db=db)
    db.commit()

    db.refresh(search_run)
    return _to_response(search_run, execution_mode=execution_mode)


@router.get("/runs/{run_id}", response_model=SearchRunResponse)
def get_discovery_run(run_id: uuid.UUID, db: Session = Depends(get_db)) -> SearchRunResponse:
    search_run = db.get(SearchRun, run_id)
    if search_run is None:
        raise AppError(
            f"SearchRun {run_id} não encontrado.",
            code="search_run_not_found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return _to_response(search_run)


class SearchRunListResponse(BaseModel):
    items: list[SearchRunResponse]
    total: int
    limit: int
    offset: int


@router.get("/runs", response_model=SearchRunListResponse)
def list_discovery_runs(
    db: Session = Depends(get_db),
    status_filter: SearchRunStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> SearchRunListResponse:
    """Lista `SearchRun` mais recentes primeiro — usado pela tela
    "Pesquisas" do Dashboard (Fase 5). Somente leitura; nenhuma lógica de
    execução nova (ver `create_discovery_search` acima, inalterado)."""
    stmt = db.query(SearchRun)
    if status_filter is not None:
        stmt = stmt.filter(SearchRun.status == status_filter)

    total = stmt.with_entities(func.count(SearchRun.id)).scalar() or 0
    runs = stmt.order_by(SearchRun.created_at.desc()).limit(limit).offset(offset).all()

    return SearchRunListResponse(
        items=[_to_response(run) for run in runs], total=total, limit=limit, offset=offset
    )
