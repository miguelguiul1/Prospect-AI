"""Consultas de leitura agregadas para o Dashboard (Fase 5).

Nenhuma regra de negócio nova vive aqui — só leitura/composição do que as
Fases 0-4 já persistem (`Company`, `CompanySource`, `Evidence`,
`AuditSnapshot`, `WebsiteQuality`, `OpportunityScore`, `SalesBrief`).
Opportunity Score continua calculado exclusivamente por
`app.domains.scoring.service.OpportunityScoringService`; Website Quality
continua calculado exclusivamente por `app.domains.audit.service.
DigitalAuditService`. Este módulo nunca recalcula nada, só consulta.

"Mais recente" é sempre por `AuditSnapshot.created_at` — uma empresa pode
ter várias auditorias ao longo do tempo (histórico preservado desde a Fase
3); o Dashboard sempre mostra a mais recente, nunca uma agregação entre
execuções diferentes.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, joinedload

from app.domains.audit.enums import AuditStatus
from app.domains.audit.models import AuditSnapshot, WebsiteQuality
from app.domains.briefing.models import SalesBrief
from app.domains.companies.models import Category, Company, Region
from app.domains.evidence.enums import ConfidenceLevel, DataState
from app.domains.evidence.models import Evidence
from app.domains.identity.models import CompanySource
from app.domains.scoring.models import OpportunityScore, OpportunityTier


@dataclass(frozen=True)
class CompanyListItem:
    id: uuid.UUID
    canonical_name: str
    category_name: str | None
    category_slug: str | None
    region_name: str | None
    region_state: str | None
    created_at_iso: str

    has_audit: bool
    audit_status: AuditStatus | None
    site_state: DataState | None
    website_quality_score: float | None

    opportunity_score: float | None
    opportunity_tier: OpportunityTier | None
    opportunity_confidence: ConfidenceLevel | None


@dataclass(frozen=True)
class CompanyListPage:
    items: list[CompanyListItem]
    total: int
    limit: int
    offset: int


@dataclass(frozen=True)
class FilterOptions:
    """Valores realmente usados por alguma `Company` — nunca uma lista
    inventada no frontend. `Category`/`Region` só ganham uma linha quando
    o Discovery de fato encontra uma empresa com aquela categoria/região
    (`app.domains.discovery.persistence.find_or_create_category`/
    `find_or_create_region`), então listar todas as linhas dessas tabelas
    já é, por construção, "as opções em uso"."""

    categories: list[Category]
    regions: list[Region]


def list_filter_options(db: Session) -> FilterOptions:
    categories = db.query(Category).order_by(Category.name.asc()).all()
    regions = db.query(Region).order_by(Region.name.asc()).all()
    return FilterOptions(categories=categories, regions=regions)


@dataclass(frozen=True)
class CompanyDetail:
    company: Company
    sources: list[CompanySource]
    evidence: list[Evidence]
    latest_audit: AuditSnapshot | None
    latest_website_quality: WebsiteQuality | None
    latest_score: OpportunityScore | None
    latest_brief: SalesBrief | None


def _latest_audit_snapshot_subquery():
    """Uma linha por `company_id` com o `created_at` máximo — usada para
    juntar de volta a `AuditSnapshot` mais recente de cada empresa em uma
    única consulta (nunca N+1 consultas por empresa listada).

    Limitação aceita: se duas auditorias da mesma empresa tiverem
    `created_at` idênticos (mesmo timestamp, o que a granularidade de
    microssegundos do banco torna extremamente improvável em uso real),
    ambas casam com o `JOIN` e a empresa pode aparecer duplicada na
    listagem. Documentado em `docs/dashboard.md`.
    """
    return (
        select(
            AuditSnapshot.company_id.label("company_id"),
            func.max(AuditSnapshot.created_at).label("max_created_at"),
        )
        .group_by(AuditSnapshot.company_id)
        .subquery()
    )


def list_companies(
    db: Session,
    *,
    q: str | None = None,
    tier: OpportunityTier | None = None,
    min_score: float | None = None,
    max_score: float | None = None,
    site_state: DataState | None = None,
    category_slug: str | None = None,
    region_name: str | None = None,
    audited: bool | None = None,
    sort_by: str = "created_at",
    limit: int = 50,
    offset: int = 0,
) -> CompanyListPage:
    latest_audit_sq = _latest_audit_snapshot_subquery()

    latest_audit = (
        select(AuditSnapshot)
        .join(
            latest_audit_sq,
            (AuditSnapshot.company_id == latest_audit_sq.c.company_id)
            & (AuditSnapshot.created_at == latest_audit_sq.c.max_created_at),
        )
        .subquery()
    )

    stmt = (
        select(
            Company,
            Category.name.label("category_name"),
            Category.slug.label("category_slug"),
            Region.name.label("region_name"),
            Region.state.label("region_state"),
            latest_audit.c.id.label("audit_id"),
            latest_audit.c.status.label("audit_status"),
            latest_audit.c.site_state.label("site_state"),
            WebsiteQuality.score.label("website_quality_score"),
            OpportunityScore.score.label("opportunity_score"),
            OpportunityScore.tier.label("opportunity_tier"),
            OpportunityScore.confidence.label("opportunity_confidence"),
        )
        .outerjoin(Category, Company.category_id == Category.id)
        .outerjoin(Region, Company.region_id == Region.id)
        .outerjoin(latest_audit, latest_audit.c.company_id == Company.id)
        .outerjoin(WebsiteQuality, WebsiteQuality.audit_snapshot_id == latest_audit.c.id)
        .outerjoin(OpportunityScore, OpportunityScore.audit_snapshot_id == latest_audit.c.id)
    )

    if q:
        stmt = stmt.where(Company.canonical_name.ilike(f"%{q}%"))
    if tier is not None:
        stmt = stmt.where(OpportunityScore.tier == tier)
    if min_score is not None:
        stmt = stmt.where(OpportunityScore.score >= min_score)
    if max_score is not None:
        stmt = stmt.where(OpportunityScore.score <= max_score)
    if site_state is not None:
        stmt = stmt.where(latest_audit.c.site_state == site_state)
    if category_slug:
        stmt = stmt.where(Category.slug == category_slug)
    if region_name:
        stmt = stmt.where(Region.name == region_name)
    if audited is True:
        stmt = stmt.where(latest_audit.c.id.is_not(None))
    elif audited is False:
        stmt = stmt.where(latest_audit.c.id.is_(None))

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    if sort_by == "opportunity_score":
        # `nulls_last()`: empresas sem score calculado ainda vão para o
        # final da lista de prioridade — nunca para o topo por acidente de
        # ordenação (NULL primeiro é o padrão em alguns bancos).
        stmt = stmt.order_by(OpportunityScore.score.desc().nulls_last(), Company.created_at.desc())
    else:
        stmt = stmt.order_by(Company.created_at.desc())

    rows = db.execute(stmt.limit(limit).offset(offset)).all()

    items = [
        CompanyListItem(
            id=row.Company.id,
            canonical_name=row.Company.canonical_name,
            category_name=row.category_name,
            category_slug=row.category_slug,
            region_name=row.region_name,
            region_state=row.region_state,
            created_at_iso=row.Company.created_at.isoformat(),
            has_audit=row.audit_id is not None,
            audit_status=row.audit_status,
            site_state=row.site_state,
            website_quality_score=row.website_quality_score,
            opportunity_score=row.opportunity_score,
            opportunity_tier=row.opportunity_tier,
            opportunity_confidence=row.opportunity_confidence,
        )
        for row in rows
    ]

    return CompanyListPage(items=items, total=total, limit=limit, offset=offset)


# Limiar inferior do tier "medium_high" (`app.domains.scoring.scoring.classify`,
# docs/opportunity-scoring.md) — reaproveitado aqui, nunca um valor novo
# inventado só para o KPI do Dashboard.
HIGH_OPPORTUNITY_MIN_SCORE = 60.0


@dataclass(frozen=True)
class DashboardStats:
    total_companies: int
    audited_companies: int
    high_opportunity_companies: int
    average_opportunity_score: float | None


def get_dashboard_stats(db: Session) -> DashboardStats:
    """Contadores agregados para os KPI cards do Dashboard (Fase 5).

    Tudo calculado em SQL (COUNT/AVG/SUM condicional) sobre a mesma
    "auditoria mais recente por empresa" usada por `list_companies` — nunca
    busca todas as linhas para agregar em Python (ver docs/dashboard.md,
    seção "Performance"). `average_opportunity_score` é a média dos scores
    ATUAIS (um por empresa, o mais recente), não de todo o histórico de
    scores já calculados.
    """
    latest_audit_sq = _latest_audit_snapshot_subquery()
    latest_audit = (
        select(AuditSnapshot.id, AuditSnapshot.company_id)
        .join(
            latest_audit_sq,
            (AuditSnapshot.company_id == latest_audit_sq.c.company_id)
            & (AuditSnapshot.created_at == latest_audit_sq.c.max_created_at),
        )
        .subquery()
    )

    total_companies = db.scalar(select(func.count(Company.id))) or 0
    audited_companies = db.scalar(select(func.count(func.distinct(latest_audit.c.company_id)))) or 0

    agg_row = db.execute(
        select(
            func.avg(OpportunityScore.score).label("avg_score"),
            func.sum(case((OpportunityScore.score >= HIGH_OPPORTUNITY_MIN_SCORE, 1), else_=0)).label("high_count"),
        )
        .select_from(latest_audit)
        .join(OpportunityScore, OpportunityScore.audit_snapshot_id == latest_audit.c.id)
    ).one()

    average_score = agg_row.avg_score
    return DashboardStats(
        total_companies=total_companies,
        audited_companies=audited_companies,
        high_opportunity_companies=int(agg_row.high_count or 0),
        average_opportunity_score=round(average_score, 1) if average_score is not None else None,
    )


def get_company_detail(db: Session, company_id: uuid.UUID) -> CompanyDetail | None:
    company = db.get(Company, company_id, options=[joinedload(Company.category), joinedload(Company.region)])
    if company is None:
        return None

    sources = (
        db.query(CompanySource)
        .filter(CompanySource.company_id == company_id)
        .order_by(CompanySource.first_seen_at.asc())
        .all()
    )

    evidence = (
        db.query(Evidence)
        .filter(Evidence.company_id == company_id, Evidence.superseded_by_id.is_(None))
        .order_by(Evidence.field.asc())
        .all()
    )

    latest_audit = (
        db.query(AuditSnapshot)
        .filter(AuditSnapshot.company_id == company_id)
        .order_by(AuditSnapshot.created_at.desc())
        .first()
    )

    latest_score = None
    latest_quality = None
    if latest_audit is not None:
        latest_quality = latest_audit.website_quality
        latest_score = (
            db.query(OpportunityScore)
            .filter(OpportunityScore.audit_snapshot_id == latest_audit.id)
            .one_or_none()
        )

    latest_brief = (
        db.query(SalesBrief)
        .filter(SalesBrief.company_id == company_id)
        .order_by(SalesBrief.created_at.desc())
        .first()
    )

    return CompanyDetail(
        company=company,
        sources=sources,
        evidence=evidence,
        latest_audit=latest_audit,
        latest_website_quality=latest_quality,
        latest_score=latest_score,
        latest_brief=latest_brief,
    )


__all__ = [
    "CompanyListItem",
    "CompanyListPage",
    "FilterOptions",
    "DashboardStats",
    "CompanyDetail",
    "list_companies",
    "list_filter_options",
    "get_dashboard_stats",
    "get_company_detail",
]
