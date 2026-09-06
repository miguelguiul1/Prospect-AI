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

from sqlalchemy import JSON, DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import Float, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.domains.audit.enums import AuditStatus
from app.domains.evidence.enums import ConfidenceLevel, DataState

if TYPE_CHECKING:
    from app.domains.companies.models import Company
    from app.domains.evidence.models import Evidence
    from app.domains.scoring.models import OpportunityScore


def _now() -> datetime:
    return datetime.now(timezone.utc)


class AuditSnapshot(Base):
    """Uma execução de auditoria digital sobre uma `Company`.

    `run_id` correlaciona esta auditoria com os logs/observabilidade da
    execução que a gerou (arquitetura v0.2, seção 20). `presence_level`
    permanece um placeholder — sua semântica na v0.2 (síntese de presença
    incluindo redes sociais, não só o website) é mais ampla do que o que a
    Fase 3 avalia; `site_state` é o que o Digital Audit de fato preenche.
    """

    __tablename__ = "audit_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"), nullable=False, index=True)
    run_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)

    presence_level: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # --- Fase 3 ---------------------------------------------------------
    website_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    site_state: Mapped[DataState | None] = mapped_column(
        SAEnum(DataState, native_enum=False, length=20), nullable=True
    )
    status: Mapped[AuditStatus] = mapped_column(
        SAEnum(AuditStatus, native_enum=False, length=20), nullable=False, default=AuditStatus.PENDING
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # ---------------------------------------------------------------------

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
    """Website Quality Score — separado do Opportunity Score (Fase 4).

    `components` guarda o detalhamento por dimensão (segurança/SEO/
    conteúdo/UX/técnico); `limitations` registra por que o score pode estar
    incompleto (ex.: resposta truncada); `confidence` é `None` quando
    `score` também é `None` (site não confirmado como acessível — ver
    `app.domains.audit.scoring`).
    """

    __tablename__ = "website_quality_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    audit_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("audit_snapshots.id"), nullable=False, unique=True, index=True
    )
    signals: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # --- Fase 3 ---------------------------------------------------------
    components: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    confidence: Mapped[ConfidenceLevel | None] = mapped_column(
        SAEnum(ConfidenceLevel, native_enum=False, length=20), nullable=True
    )
    limitations: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # ---------------------------------------------------------------------

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)

    audit_snapshot: Mapped["AuditSnapshot"] = relationship(back_populates="website_quality")
