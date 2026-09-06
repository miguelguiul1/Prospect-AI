"""Modelos do domínio `scoring`.

`OpportunityScore` é relacionado a um `AuditSnapshot` específico — nunca
diretamente e de forma permanente a uma `Company` — porque a oportunidade
comercial muda a cada nova auditoria, e o histórico de como ela evoluiu
precisa ser preservado (arquitetura v0.2, seções 06 e 14).
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, Float
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.domains.audit.models import AuditSnapshot


def _now() -> datetime:
    return datetime.now(timezone.utc)


class OpportunityTier(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class OpportunityScore(Base):
    """Placeholder estrutural do Opportunity Score (Fase 4).

    `score`, `tier`, `breakdown` e `recommended_product` permanecem nulos
    até a fórmula de pontuação (arquitetura v0.2, seção 14) ser
    implementada.
    """

    __tablename__ = "opportunity_scores"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    audit_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("audit_snapshots.id"), nullable=False, unique=True, index=True
    )

    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    tier: Mapped[OpportunityTier | None] = mapped_column(
        SAEnum(OpportunityTier, native_enum=False, length=20), nullable=True
    )
    breakdown: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    recommended_product: Mapped[str | None] = mapped_column(String(120), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)

    audit_snapshot: Mapped["AuditSnapshot"] = relationship(back_populates="opportunity_score")
