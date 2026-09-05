"""Modelo do domínio `evidence`.

Evidence é um log append-only: uma nova observação nunca sobrescreve uma
linha existente. Ela é gravada como uma nova `Evidence`, e a antiga recebe
`superseded_by_id` apontando para a nova — o "valor atual" de um campo é
sempre a evidência não superada mais recente. Ver arquitetura v0.2, seção 08.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, Float
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.domains.evidence.enums import ConfidenceLevel, DataState, EvidenceMethod

if TYPE_CHECKING:
    from app.domains.audit.models import AuditSnapshot
    from app.domains.companies.models import Company


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Evidence(Base):
    __tablename__ = "evidence"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"), nullable=False, index=True)
    audit_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("audit_snapshots.id"), nullable=True, index=True
    )

    field: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    value: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    state: Mapped[DataState] = mapped_column(
        SAEnum(DataState, native_enum=False, length=20), nullable=False
    )

    source: Mapped[str] = mapped_column(String(60), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    method: Mapped[EvidenceMethod] = mapped_column(
        SAEnum(EvidenceMethod, native_enum=False, length=30), nullable=False
    )
    confidence: Mapped[ConfidenceLevel] = mapped_column(
        SAEnum(ConfidenceLevel, native_enum=False, length=20), nullable=False
    )
    match_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    raw_reference: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)

    superseded_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("evidence.id"), nullable=True)
    superseded_by: Mapped["Evidence | None"] = relationship(remote_side=[id])

    company: Mapped["Company"] = relationship(back_populates="evidences")
    audit_snapshot: Mapped["AuditSnapshot | None"] = relationship(back_populates="evidences")

    def mark_superseded_by(self, newer: "Evidence") -> None:
        """Marca esta evidência como superada por uma mais recente.

        Nunca edita `value`/`state` no lugar — só aponta para a substituta,
        preservando o histórico completo (seção 08 da arquitetura v0.2).
        """
        self.superseded_by_id = newer.id
