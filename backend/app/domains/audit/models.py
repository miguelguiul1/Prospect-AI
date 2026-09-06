"""Modelos do domínio `audit`.

Inclui `WebsiteQuality` propositalmente: embora a arquitetura v0.2 trate o
Website Quality Score como um conceito distinto do Opportunity Score, ele é
um subproduto de uma execução de auditoria (1:1 com `AuditSnapshot`), então
sua estrutura de dados vive junto do estágio que a produz. O domínio
`scoring` guarda apenas `OpportunityScore`. Esta é uma decisão de
organização de código, não uma mudança da arquitetura v0.2 — ver
docs/data-model.md, seção "Desvios de organização em relação ao documento
de arquitetura".
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.domains.companies.models import Company
    from app.domains.evidence.models import Evidence
    from app.domains.scoring.models import OpportunityScore


def _now() -> datetime:
    return datetime.now(timezone.utc)


class AuditSnapshot(Base):
    """Uma execução de auditoria digital sobre uma `Company`.

    `run_id` correlaciona esta auditoria com os logs/observabilidade da
    execução que a gerou (arquitetura v0.2, seção 20). `presence_level` é
    calculado pelo Digital Auditor (Fase 3); nesta fase permanece sempre
    nulo — a coluna existe para não exigir uma migration destrutiva depois.
    """

    __tablename__ = "audit_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"), nullable=False, index=True)
    run_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)

    presence_level: Mapped[str | None] = mapped_column(String(20), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)

    company: Mapped["Company"] = relationship(back_populates="audit_snapshots")
    evidences: Mapped[list["Evidence"]] = relationship(back_populates="audit_snapshot")
    website_quality: Mapped["WebsiteQuality | None"] = relationship(
        back_populates="audit_snapshot", uselist=False, cascade="all, delete-orphan"
    )
    opportunity_score: Mapped["OpportunityScore | None"] = relationship(
        back_populates="audit_snapshot", uselist=False, cascade="all, delete-orphan"
    )


class WebsiteQuality(Base):
    """Placeholder estrutural do Website Quality Score (Fase 3).

    `signals` e `score` permanecem nulos até o Digital Auditor calcular os
    sinais determinísticos descritos na arquitetura v0.2, seção 12.
    """

    __tablename__ = "website_quality_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    audit_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("audit_snapshots.id"), nullable=False, unique=True, index=True
    )
    signals: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)

    audit_snapshot: Mapped["AuditSnapshot"] = relationship(back_populates="website_quality")
