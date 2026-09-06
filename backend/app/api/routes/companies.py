"""API HTTP de leitura agregada para o Dashboard (Fase 5).

`GET /api/companies` lista empresas com a auditoria/score mais recentes já
embutidos (evita N chamadas do frontend para montar uma tabela). `GET
/api/companies/{company_id}` devolve tudo que a tela de detalhe do
Dashboard precisa em uma única chamada: identidade, fontes (Discovery),
Evidence atual, auditoria/Website Quality mais recentes, Opportunity Score
mais recente e o Sales Brief mais recente.

Nenhuma regra de negócio nova: todo cálculo (Website Quality, Opportunity
Score, Sales Brief) continua exclusivamente nos serviços das Fases 3/4 —
ver `app.domains.companies.queries`. Para disparar uma nova auditoria,
recalcular o score ou gerar um briefing, o frontend chama as rotas já
existentes (`POST /api/audit/{id}`, `POST /api/scoring/{id}`,
`POST /api/sales-brief/{id}`), nunca uma rota nova.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.session import get_db
from app.domains.audit.enums import AuditStatus
from app.domains.companies.queries import (
    get_company_detail,
    get_dashboard_stats,
    list_companies,
    list_filter_options,
)
from app.domains.evidence.enums import ConfidenceLevel, DataState, EvidenceMethod
from app.domains.scoring.models import OpportunityTier

router = APIRouter(prefix="/api/companies", tags=["companies"])


class CompanyListItemResponse(BaseModel):
    id: uuid.UUID
    canonical_name: str
    category_name: str | None
    category_slug: str | None
    region_name: str | None
    region_state: str | None
    created_at: str

    has_audit: bool
    audit_status: AuditStatus | None
    site_state: DataState | None
    website_quality_score: float | None

    opportunity_score: float | None
    opportunity_tier: OpportunityTier | None
    opportunity_confidence: ConfidenceLevel | None


class CompanyListResponse(BaseModel):
    items: list[CompanyListItemResponse]
    total: int
    limit: int
    offset: int


class CompanySourceResponse(BaseModel):
    id: uuid.UUID
    source: str
    external_id: str
    source_url: str | None
    latitude: float | None
    longitude: float | None
    confidence: ConfidenceLevel
    first_seen_at: datetime
    last_seen_at: datetime


class EvidenceResponse(BaseModel):
    id: uuid.UUID
    field: str
    value: str | None
    state: DataState
    source: str
    source_url: str | None
    method: EvidenceMethod
    confidence: ConfidenceLevel
    collected_at: datetime


class WebsiteQualityResponse(BaseModel):
    score: float | None
    components: dict | None
    confidence: ConfidenceLevel | None
    limitations: list | None
    signals: dict | None


class AuditSnapshotResponse(BaseModel):
    id: uuid.UUID
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


class OpportunityScoreResponse(BaseModel):
    id: uuid.UUID
    score: float | None
    tier: OpportunityTier | None
    confidence: ConfidenceLevel | None
    scoring_version: str
    breakdown: dict | None
    created_at: datetime
    updated_at: datetime


class SalesBriefResponse(BaseModel):
    id: uuid.UUID
    status: str
    content: dict | None
    provider: str | None
    model: str | None
    error_code: str | None
    error_message: str | None
    generated_at: datetime


class CompanyDetailResponse(BaseModel):
    id: uuid.UUID
    canonical_name: str
    status: str
    category_name: str | None
    category_slug: str | None
    region_name: str | None
    region_state: str | None
    created_at: datetime

    sources: list[CompanySourceResponse]
    evidence: list[EvidenceResponse]
    latest_audit: AuditSnapshotResponse | None
    latest_score: OpportunityScoreResponse | None
    latest_brief: SalesBriefResponse | None


@router.get("", response_model=CompanyListResponse)
def get_companies(
    db: Session = Depends(get_db),
    q: str | None = Query(default=None, max_length=255),
    tier: OpportunityTier | None = None,
    min_score: float | None = Query(default=None, ge=0, le=100),
    max_score: float | None = Query(default=None, ge=0, le=100),
    site_state: DataState | None = None,
    category: str | None = Query(default=None, max_length=80),
    region: str | None = Query(default=None, max_length=120),
    audited: bool | None = None,
    sort_by: str = Query(default="created_at", pattern="^(created_at|opportunity_score)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> CompanyListResponse:
    page = list_companies(
        db,
        q=q,
        tier=tier,
        min_score=min_score,
        max_score=max_score,
        site_state=site_state,
        category_slug=category,
        region_name=region,
        audited=audited,
        sort_by=sort_by,
        limit=limit,
        offset=offset,
    )
    return CompanyListResponse(
        items=[
            CompanyListItemResponse(
                id=item.id,
                canonical_name=item.canonical_name,
                category_name=item.category_name,
                category_slug=item.category_slug,
                region_name=item.region_name,
                region_state=item.region_state,
                created_at=item.created_at_iso,
                has_audit=item.has_audit,
                audit_status=item.audit_status,
                site_state=item.site_state,
                website_quality_score=item.website_quality_score,
                opportunity_score=item.opportunity_score,
                opportunity_tier=item.opportunity_tier,
                opportunity_confidence=item.opportunity_confidence,
            )
            for item in page.items
        ],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
    )


class CategoryOptionResponse(BaseModel):
    slug: str
    name: str


class RegionOptionResponse(BaseModel):
    name: str
    state: str | None


class FilterOptionsResponse(BaseModel):
    categories: list[CategoryOptionResponse]
    regions: list[RegionOptionResponse]


@router.get("/meta/filters", response_model=FilterOptionsResponse)
def get_filter_options(db: Session = Depends(get_db)) -> FilterOptionsResponse:
    """Opções reais de filtro (categorias/regiões que pelo menos uma
    `Company` já usa) — nunca uma lista inventada no frontend."""
    options = list_filter_options(db)
    return FilterOptionsResponse(
        categories=[CategoryOptionResponse(slug=c.slug, name=c.name) for c in options.categories],
        regions=[RegionOptionResponse(name=r.name, state=r.state) for r in options.regions],
    )


class DashboardStatsResponse(BaseModel):
    total_companies: int
    audited_companies: int
    high_opportunity_companies: int
    average_opportunity_score: float | None


@router.get("/meta/stats", response_model=DashboardStatsResponse)
def get_stats(db: Session = Depends(get_db)) -> DashboardStatsResponse:
    """KPIs agregados do Dashboard (Fase 5) — calculados em SQL, nunca
    aproximados a partir de uma página parcial de resultados."""
    stats = get_dashboard_stats(db)
    return DashboardStatsResponse(
        total_companies=stats.total_companies,
        audited_companies=stats.audited_companies,
        high_opportunity_companies=stats.high_opportunity_companies,
        average_opportunity_score=stats.average_opportunity_score,
    )


@router.get("/{company_id}", response_model=CompanyDetailResponse)
def get_company(company_id: uuid.UUID, db: Session = Depends(get_db)) -> CompanyDetailResponse:
    detail = get_company_detail(db, company_id)
    if detail is None:
        raise AppError(
            f"Company {company_id} não encontrada.",
            code="company_not_found",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    company = detail.company
    audit = detail.latest_audit
    quality = detail.latest_website_quality
    score = detail.latest_score
    brief = detail.latest_brief

    return CompanyDetailResponse(
        id=company.id,
        canonical_name=company.canonical_name,
        status=company.status.value,
        category_name=company.category.name if company.category else None,
        category_slug=company.category.slug if company.category else None,
        region_name=company.region.name if company.region else None,
        region_state=company.region.state if company.region else None,
        created_at=company.created_at,
        sources=[
            CompanySourceResponse(
                id=s.id,
                source=s.source,
                external_id=s.external_id,
                source_url=s.source_url,
                latitude=s.latitude,
                longitude=s.longitude,
                confidence=s.confidence,
                first_seen_at=s.first_seen_at,
                last_seen_at=s.last_seen_at,
            )
            for s in detail.sources
        ],
        evidence=[
            EvidenceResponse(
                id=e.id,
                field=e.field,
                value=e.value,
                state=e.state,
                source=e.source,
                source_url=e.source_url,
                method=e.method,
                confidence=e.confidence,
                collected_at=e.collected_at,
            )
            for e in detail.evidence
        ],
        latest_audit=(
            AuditSnapshotResponse(
                id=audit.id,
                run_id=audit.run_id,
                status=audit.status,
                site_state=audit.site_state,
                website_url=audit.website_url,
                error_code=audit.error_code,
                error_message=audit.error_message,
                started_at=audit.started_at,
                finished_at=audit.finished_at,
                created_at=audit.created_at,
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
            )
            if audit is not None
            else None
        ),
        latest_score=(
            OpportunityScoreResponse(
                id=score.id,
                score=score.score,
                tier=score.tier,
                confidence=score.confidence,
                scoring_version=score.scoring_version,
                breakdown=score.breakdown,
                created_at=score.created_at,
                updated_at=score.updated_at,
            )
            if score is not None
            else None
        ),
        latest_brief=(
            SalesBriefResponse(
                id=brief.id,
                status=brief.status.value,
                content=brief.content,
                provider=brief.provider,
                model=brief.model,
                error_code=brief.error_code,
                error_message=brief.error_message,
                generated_at=brief.generated_at,
            )
            if brief is not None
            else None
        ),
    )
