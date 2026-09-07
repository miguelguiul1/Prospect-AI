"""API HTTP do núcleo do CRM: Opportunity + Pipeline (Fase 7).

Toda rota depende de `get_current_user` — não há nenhum endpoint público
neste router. Toda leitura/escrita de uma `Opportunity` específica passa por
`app.domains.crm.authorization.get_owned_opportunity_or_404`, nunca confia
em `owner_id` do payload do cliente (Prompt 11, seção 4.2).

`GET /{id}` é o "centro de contexto comercial" (Prompt 11, seção 15.4):
reaproveita `app.domains.companies.queries.get_company_detail` (Fase 5) para
Identidade/Intelligence — nenhuma lógica de Company/Evidence/Score/Brief é
duplicada aqui, só composta.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.session import get_db
from app.domains.auth.dependencies import get_current_user
from app.domains.auth.models import User
from app.domains.companies.queries import get_company_detail
from app.domains.crm.authorization import get_owned_opportunity_or_404
from app.domains.crm.enums import OpportunityPriority, OpportunityStatus
from app.domains.crm.models import Contact, Opportunity, PipelineStage
from app.domains.crm.queries import get_opportunity_kpis, list_opportunities_for_owner
from app.domains.crm.schemas import (
    OpportunityCloseRequest,
    OpportunityCreateRequest,
    OpportunityOwnerChangeRequest,
    OpportunityStageChangeRequest,
)
from app.domains.crm.service import ActivityService, ContactService, OpportunityService, PipelineService
from app.domains.scoring.models import OpportunityTier

router = APIRouter(prefix="/api/crm", tags=["crm"])


class PipelineStageResponse(BaseModel):
    id: uuid.UUID
    key: str
    name: str
    order: int
    is_won: bool
    is_lost: bool


def _stage_response(stage: PipelineStage) -> PipelineStageResponse:
    return PipelineStageResponse(
        id=stage.id, key=stage.key, name=stage.name, order=stage.order, is_won=stage.is_won, is_lost=stage.is_lost
    )


class OpportunitySummaryResponse(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    company_name: str
    category_name: str | None
    region_name: str | None
    owner_id: uuid.UUID
    owner_name: str
    stage: PipelineStageResponse
    status: OpportunityStatus
    priority: OpportunityPriority
    opportunity_score: float | None
    opportunity_tier: OpportunityTier | None
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None


class OpportunityListResponse(BaseModel):
    items: list[OpportunitySummaryResponse]
    total: int
    limit: int
    offset: int


class PipelineBoardColumn(BaseModel):
    stage: PipelineStageResponse
    opportunities: list[OpportunitySummaryResponse]


class PipelineBoardResponse(BaseModel):
    columns: list[PipelineBoardColumn]


class OpportunityKPIsResponse(BaseModel):
    open_count: int
    new_count: int
    in_negotiation_count: int
    meetings_count: int
    won_count: int
    lost_count: int
    overdue_tasks_count: int


class ContactSummaryResponse(BaseModel):
    id: uuid.UUID
    name: str
    role: str | None
    email: str | None
    phone: str | None
    validation_status: str


class ActivitySummaryResponse(BaseModel):
    id: uuid.UUID
    type: str
    title: str | None
    description: str | None
    status: str | None
    due_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


class OpportunityDetailResponse(BaseModel):
    id: uuid.UUID
    status: OpportunityStatus
    priority: OpportunityPriority
    stage: PipelineStageResponse
    owner_id: uuid.UUID
    owner_name: str
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None

    # Identidade + Intelligence (Company/Evidence/Score/Sales Brief) — mesmo
    # formato já usado em app.api.routes.companies.CompanyDetailResponse,
    # reaproveitado por composição em vez de duplicado.
    company_id: uuid.UUID
    company_name: str
    category_name: str | None
    region_name: str | None
    website_url: str | None
    site_state: str | None
    website_quality_score: float | None
    opportunity_score: float | None
    opportunity_tier: OpportunityTier | None
    opportunity_confidence: str | None
    opportunity_breakdown: dict | None
    sales_brief_status: str | None
    sales_brief_content: dict | None

    contacts: list[ContactSummaryResponse]
    recent_activities: list[ActivitySummaryResponse]


def _summary_response(item, owner_name: str) -> OpportunitySummaryResponse:
    opp: Opportunity = item.opportunity
    return OpportunitySummaryResponse(
        id=opp.id,
        company_id=opp.company_id,
        company_name=item.company_name,
        category_name=item.category_name,
        region_name=item.region_name,
        owner_id=opp.owner_id,
        owner_name=owner_name,
        stage=_stage_response(opp.stage),
        status=opp.status,
        priority=opp.priority,
        opportunity_score=item.opportunity_score,
        opportunity_tier=item.opportunity_tier,
        created_at=opp.created_at,
        updated_at=opp.updated_at,
        closed_at=opp.closed_at,
    )


def _contact_response(contact: Contact) -> ContactSummaryResponse:
    return ContactSummaryResponse(
        id=contact.id,
        name=contact.name,
        role=contact.role,
        email=contact.email,
        phone=contact.phone,
        validation_status=contact.validation_status.value,
    )


@router.post("/opportunities", response_model=OpportunitySummaryResponse, status_code=status.HTTP_201_CREATED)
def create_opportunity(
    payload: OpportunityCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> OpportunitySummaryResponse:
    service = OpportunityService(db)
    try:
        opportunity, created = service.create_or_get(
            company_id=payload.company_id, owner_id=current_user.id, priority=payload.priority
        )
    except LookupError as exc:
        raise AppError(str(exc), code="company_not_found", status_code=status.HTTP_404_NOT_FOUND) from exc

    if not created and opportunity.owner_id != current_user.id:
        # Já existe uma Opportunity aberta para esta empresa, mas de outro
        # usuário — nunca devolvemos os dados dela para quem não é dono
        # (isso seria um IDOR por um caminho diferente do GET direto).
        db.rollback()
        raise AppError(
            "Esta empresa já possui uma oportunidade aberta atribuída a outro usuário.",
            code="opportunity_owned_by_another_user",
            status_code=status.HTTP_409_CONFLICT,
        )

    db.commit()
    db.refresh(opportunity)
    return _summary_response_from_opportunity(db, opportunity)


def _summary_response_from_opportunity(db: Session, opportunity: Opportunity) -> OpportunitySummaryResponse:
    page = list_opportunities_for_owner(db, opportunity.owner_id, limit=1, offset=0)
    for item in page.items:
        if item.opportunity.id == opportunity.id:
            return _summary_response(item, item.opportunity.owner.name)
    # Fallback raro (ex.: acabou de ser criada e ainda não bate o order_by
    # da primeira página) — busca direta sem os campos agregados de score.
    db.refresh(opportunity)
    return OpportunitySummaryResponse(
        id=opportunity.id,
        company_id=opportunity.company_id,
        company_name=opportunity.company.canonical_name,
        category_name=opportunity.company.category.name if opportunity.company.category else None,
        region_name=opportunity.company.region.name if opportunity.company.region else None,
        owner_id=opportunity.owner_id,
        owner_name=opportunity.owner.name,
        stage=_stage_response(opportunity.stage),
        status=opportunity.status,
        priority=opportunity.priority,
        opportunity_score=None,
        opportunity_tier=None,
        created_at=opportunity.created_at,
        updated_at=opportunity.updated_at,
        closed_at=opportunity.closed_at,
    )


@router.get("/opportunities", response_model=OpportunityListResponse)
def list_opportunities(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    stage: str | None = Query(default=None, max_length=40),
    status_filter: OpportunityStatus | None = Query(default=None, alias="status"),
    priority: OpportunityPriority | None = None,
    category_id: uuid.UUID | None = None,
    region_id: uuid.UUID | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> OpportunityListResponse:
    page = list_opportunities_for_owner(
        db,
        current_user.id,
        stage_key=stage,
        status_filter=status_filter,
        priority=priority,
        category_id=category_id,
        region_id=region_id,
        limit=limit,
        offset=offset,
    )
    return OpportunityListResponse(
        items=[_summary_response(item, current_user.name) for item in page.items],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/pipeline", response_model=PipelineBoardResponse)
def get_pipeline_board(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> PipelineBoardResponse:
    stages = PipelineService(db).list_stages()
    page = list_opportunities_for_owner(db, current_user.id, limit=500, offset=0)

    by_stage: dict[uuid.UUID, list[OpportunitySummaryResponse]] = {stage.id: [] for stage in stages}
    for item in page.items:
        by_stage.setdefault(item.opportunity.stage_id, []).append(_summary_response(item, current_user.name))

    columns = [
        PipelineBoardColumn(stage=_stage_response(stage), opportunities=by_stage.get(stage.id, []))
        for stage in stages
    ]
    return PipelineBoardResponse(columns=columns)


@router.get("/kpis", response_model=OpportunityKPIsResponse)
def get_kpis(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> OpportunityKPIsResponse:
    kpis = get_opportunity_kpis(db, current_user.id)
    return OpportunityKPIsResponse(**kpis.__dict__)


@router.get("/companies/{company_id}/opportunity", response_model=OpportunitySummaryResponse | None)
def get_open_opportunity_for_company(
    company_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> OpportunitySummaryResponse | None:
    """Usado pela tela de Prospect (Prompt 11, seção 34) para decidir entre
    mostrar "Criar oportunidade" ou "Abrir no CRM". Só revela a oportunidade
    se ELA PERTENCER ao usuário atual — se existir uma aberta de outro
    usuário, o resultado é indistinguível de "nenhuma" (nunca vaza
    existência de dado de outro usuário por este caminho, mesma política de
    `app.domains.crm.authorization`)."""
    opportunity = OpportunityService(db).get_open_for_company(company_id)
    if opportunity is None or opportunity.owner_id != current_user.id:
        return None
    return _summary_response_from_opportunity(db, opportunity)


@router.get("/opportunities/{opportunity_id}", response_model=OpportunityDetailResponse)
def get_opportunity(
    opportunity_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> OpportunityDetailResponse:
    opportunity = get_owned_opportunity_or_404(db, opportunity_id, current_user)
    detail = get_company_detail(db, opportunity.company_id)
    assert detail is not None  # company_id de uma Opportunity sempre referencia uma Company existente

    contacts = ContactService(db).list_for_company(opportunity.company_id)
    activities = ActivityService(db).timeline(opportunity.id, limit=20)

    score = detail.latest_score
    audit = detail.latest_audit
    quality = detail.latest_website_quality
    brief = detail.latest_brief

    return OpportunityDetailResponse(
        id=opportunity.id,
        status=opportunity.status,
        priority=opportunity.priority,
        stage=_stage_response(opportunity.stage),
        owner_id=opportunity.owner_id,
        owner_name=opportunity.owner.name,
        created_at=opportunity.created_at,
        updated_at=opportunity.updated_at,
        closed_at=opportunity.closed_at,
        company_id=detail.company.id,
        company_name=detail.company.canonical_name,
        category_name=detail.company.category.name if detail.company.category else None,
        region_name=detail.company.region.name if detail.company.region else None,
        website_url=audit.website_url if audit else None,
        site_state=audit.site_state.value if audit and audit.site_state else None,
        website_quality_score=quality.score if quality else None,
        opportunity_score=score.score if score else None,
        opportunity_tier=score.tier if score else None,
        opportunity_confidence=score.confidence.value if score and score.confidence else None,
        opportunity_breakdown=score.breakdown if score else None,
        sales_brief_status=brief.status.value if brief else None,
        sales_brief_content=brief.content if brief else None,
        contacts=[_contact_response(c) for c in contacts],
        recent_activities=[
            ActivitySummaryResponse(
                id=a.id,
                type=a.type.value,
                title=a.title,
                description=a.description,
                status=a.status.value if a.status else None,
                due_at=a.due_at,
                completed_at=a.completed_at,
                created_at=a.created_at,
            )
            for a in activities
        ],
    )


@router.patch("/opportunities/{opportunity_id}/stage", response_model=OpportunitySummaryResponse)
def change_stage(
    opportunity_id: uuid.UUID,
    payload: OpportunityStageChangeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> OpportunitySummaryResponse:
    opportunity = get_owned_opportunity_or_404(db, opportunity_id, current_user)
    try:
        OpportunityService(db).change_stage(opportunity, stage_key=payload.stage_key, user_id=current_user.id)
    except ValueError as exc:
        raise AppError(str(exc), code="invalid_stage_change", status_code=status.HTTP_409_CONFLICT) from exc
    db.commit()
    db.refresh(opportunity)
    return _summary_response_from_opportunity(db, opportunity)


@router.patch("/opportunities/{opportunity_id}/owner", response_model=OpportunitySummaryResponse)
def change_owner(
    opportunity_id: uuid.UUID,
    payload: OpportunityOwnerChangeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> OpportunitySummaryResponse:
    opportunity = get_owned_opportunity_or_404(db, opportunity_id, current_user)
    try:
        OpportunityService(db).change_owner(opportunity, new_owner_id=payload.owner_id, changed_by=current_user.id)
    except ValueError as exc:
        raise AppError(str(exc), code="invalid_owner", status_code=status.HTTP_422_UNPROCESSABLE_CONTENT) from exc
    db.commit()
    db.refresh(opportunity)
    # Após a transferência, o usuário atual pode não ser mais o dono — a
    # resposta ainda reflete o estado novo (ele só não conseguirá mais
    # buscar/alterar esta Opportunity em requisições futuras).
    return _summary_response_from_opportunity(db, opportunity)


@router.post("/opportunities/{opportunity_id}/close", response_model=OpportunitySummaryResponse)
def close_opportunity(
    opportunity_id: uuid.UUID,
    payload: OpportunityCloseRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> OpportunitySummaryResponse:
    opportunity = get_owned_opportunity_or_404(db, opportunity_id, current_user)
    try:
        OpportunityService(db).close(
            opportunity, outcome=payload.outcome, reason=payload.reason, user_id=current_user.id
        )
    except ValueError as exc:
        raise AppError(str(exc), code="invalid_close", status_code=status.HTTP_409_CONFLICT) from exc
    db.commit()
    db.refresh(opportunity)
    return _summary_response_from_opportunity(db, opportunity)


@router.post("/opportunities/{opportunity_id}/reopen", response_model=OpportunitySummaryResponse)
def reopen_opportunity(
    opportunity_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> OpportunitySummaryResponse:
    opportunity = get_owned_opportunity_or_404(db, opportunity_id, current_user)
    try:
        OpportunityService(db).reopen(opportunity, user_id=current_user.id)
    except ValueError as exc:
        raise AppError(str(exc), code="invalid_reopen", status_code=status.HTTP_409_CONFLICT) from exc
    db.commit()
    db.refresh(opportunity)
    return _summary_response_from_opportunity(db, opportunity)


@router.get("/opportunities/{opportunity_id}/timeline", response_model=list[ActivitySummaryResponse])
def get_timeline(
    opportunity_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[ActivitySummaryResponse]:
    get_owned_opportunity_or_404(db, opportunity_id, current_user)
    activities = ActivityService(db).timeline(opportunity_id, limit=limit, offset=offset)
    return [
        ActivitySummaryResponse(
            id=a.id,
            type=a.type.value,
            title=a.title,
            description=a.description,
            status=a.status.value if a.status else None,
            due_at=a.due_at,
            completed_at=a.completed_at,
            created_at=a.created_at,
        )
        for a in activities
    ]
