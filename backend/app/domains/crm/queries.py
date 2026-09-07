"""Consultas de leitura agregadas do domínio `crm` (Fase 7).

Mesmo espírito de `app.domains.companies.queries` (Fase 5): nenhuma regra de
negócio nova, só composição eficiente (sem N+1) do que `crm`/`scoring`/
`companies` já persistem, sempre já filtrado por `owner_id` — nenhuma
função aqui devolve uma `Opportunity` de outro usuário.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.domains.audit.models import AuditSnapshot
from app.domains.companies.models import Category, Company, Region
from app.domains.crm.enums import ActivityStatus, ActivityType, OpportunityPriority, OpportunityStatus
from app.domains.crm.models import Activity, Opportunity, PipelineStage
from app.domains.scoring.models import OpportunityScore, OpportunityTier


def _latest_audit_snapshot_subquery():
    return (
        select(
            AuditSnapshot.company_id.label("company_id"),
            func.max(AuditSnapshot.created_at).label("max_created_at"),
        )
        .group_by(AuditSnapshot.company_id)
        .subquery()
    )


@dataclass(frozen=True)
class OpportunityListItem:
    opportunity: Opportunity
    company_name: str
    category_name: str | None
    region_name: str | None
    opportunity_score: float | None
    opportunity_tier: OpportunityTier | None


@dataclass(frozen=True)
class OpportunityListPage:
    items: list[OpportunityListItem]
    total: int
    limit: int
    offset: int


def list_opportunities_for_owner(
    db: Session,
    owner_id: uuid.UUID,
    *,
    stage_key: str | None = None,
    status_filter: OpportunityStatus | None = None,
    priority: OpportunityPriority | None = None,
    category_id: uuid.UUID | None = None,
    region_id: uuid.UUID | None = None,
    limit: int = 50,
    offset: int = 0,
) -> OpportunityListPage:
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

    stmt = (
        select(
            Opportunity,
            Company.canonical_name,
            Category.name,
            Region.name,
            OpportunityScore.score,
            OpportunityScore.tier,
        )
        .join(Company, Company.id == Opportunity.company_id)
        .outerjoin(Category, Company.category_id == Category.id)
        .outerjoin(Region, Company.region_id == Region.id)
        .outerjoin(latest_audit, latest_audit.c.company_id == Company.id)
        .outerjoin(OpportunityScore, OpportunityScore.audit_snapshot_id == latest_audit.c.id)
        .options(joinedload(Opportunity.stage), joinedload(Opportunity.owner))
        .where(Opportunity.owner_id == owner_id)
    )
    if stage_key is not None:
        stmt = stmt.join(PipelineStage, PipelineStage.id == Opportunity.stage_id).where(
            PipelineStage.key == stage_key
        )
    if status_filter is not None:
        stmt = stmt.where(Opportunity.status == status_filter)
    if priority is not None:
        stmt = stmt.where(Opportunity.priority == priority)
    if category_id is not None:
        stmt = stmt.where(Company.category_id == category_id)
    if region_id is not None:
        stmt = stmt.where(Company.region_id == region_id)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.execute(stmt.order_by(Opportunity.updated_at.desc()).limit(limit).offset(offset)).all()

    items = [
        OpportunityListItem(
            opportunity=row[0],
            company_name=row[1],
            category_name=row[2],
            region_name=row[3],
            opportunity_score=row[4],
            opportunity_tier=row[5],
        )
        for row in rows
    ]
    return OpportunityListPage(items=items, total=total, limit=limit, offset=offset)


@dataclass(frozen=True)
class OpportunityKPIs:
    open_count: int
    new_count: int
    in_negotiation_count: int
    meetings_count: int
    won_count: int
    lost_count: int
    overdue_tasks_count: int


def get_opportunity_kpis(db: Session, owner_id: uuid.UUID) -> OpportunityKPIs:
    rows = (
        db.query(Opportunity.status, PipelineStage.key, func.count())
        .join(PipelineStage, PipelineStage.id == Opportunity.stage_id)
        .filter(Opportunity.owner_id == owner_id)
        .group_by(Opportunity.status, PipelineStage.key)
        .all()
    )

    open_count = 0
    new_count = 0
    in_negotiation_count = 0
    meetings_count = 0
    won_count = 0
    lost_count = 0
    for opp_status, stage_key, count in rows:
        if opp_status == OpportunityStatus.OPEN:
            open_count += count
            if stage_key == "new":
                new_count += count
            elif stage_key == "negotiation":
                in_negotiation_count += count
            elif stage_key == "meeting":
                meetings_count += count
        elif opp_status == OpportunityStatus.WON:
            won_count += count
        elif opp_status == OpportunityStatus.LOST:
            lost_count += count

    overdue_tasks_count = (
        db.query(func.count(Activity.id))
        .join(Opportunity, Opportunity.id == Activity.opportunity_id)
        .filter(
            Opportunity.owner_id == owner_id,
            Activity.type == ActivityType.TASK,
            Activity.status == ActivityStatus.OPEN,
            Activity.due_at.isnot(None),
            Activity.due_at < func.now(),
        )
        .scalar()
        or 0
    )

    return OpportunityKPIs(
        open_count=open_count,
        new_count=new_count,
        in_negotiation_count=in_negotiation_count,
        meetings_count=meetings_count,
        won_count=won_count,
        lost_count=lost_count,
        overdue_tasks_count=overdue_tasks_count,
    )


__all__ = [
    "OpportunityListItem",
    "OpportunityListPage",
    "OpportunityKPIs",
    "list_opportunities_for_owner",
    "get_opportunity_kpis",
]
