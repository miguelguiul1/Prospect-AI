"""Modelo do domínio `briefing`: Sales Brief.

`SalesBrief` é o ÚNICO artefato desta arquitetura que envolve uma chamada a
um provider de IA (ver `app.domains.briefing.providers`). Todo o resto da
Fase 4 (Opportunity Score) é determinístico — ver `app.domains.scoring`.

Histórico é preservado: cada chamada a `POST /api/sales-brief/{company_id}`
cria uma linha nova (nunca sobrescreve uma anterior), da mesma forma que uma
nova `AuditSnapshot` nunca sobrescreve a anterior. `status=FAILED` é
persistido como um resultado válido — nunca mascarado como sucesso — quando
o provider está indisponível, expira por timeout ou responde algo que não
valida contra `app.domains.briefing.schemas.SalesBriefContent`.

O vínculo com `opportunity_score_id` (não diretamente com `audit_snapshot_id`
nem só com `company_id`) ancora exatamente qual versão dos dados
(`OpportunityScore.scoring_version` + a cadeia até o `AuditSnapshot` que o
gerou) fundamentou este briefing — não é necessário um campo extra de
"versão de contexto": seguir essa referência já reconstrói tudo que foi lido.
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, Float, Integer
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.domains.companies.models import Company
    from app.domains.scoring.models import OpportunityScore


def _now() -> datetime:
    return datetime.now(timezone.utc)


class SalesBriefStatus(str, enum.Enum):
    COMPLETED = "completed"
    FAILED = "failed"


class SalesBrief(Base):
    __tablename__ = "sales_briefs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"), nullable=False, index=True)
    opportunity_score_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("opportunity_scores.id"), nullable=False, index=True
    )

    status: Mapped[SalesBriefStatus] = mapped_column(
        SAEnum(SalesBriefStatus, native_enum=False, length=20), nullable=False
    )

    # Conteúdo estruturado validado contra `SalesBriefContent` (Pydantic) —
    # nulo quando `status=FAILED`.
    content: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    provider: Mapped[str | None] = mapped_column(String(40), nullable=True)
    model: Mapped[str | None] = mapped_column(String(80), nullable=True)
    prompt_version: Mapped[str] = mapped_column(String(10), nullable=False, default="v1")

    error_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)

    duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Só preenchidos quando o próprio provider os retorna — nunca estimados
    # ou inventados (ver docs/sales-brief.md, seção "custos/uso").
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)

    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)

    company: Mapped["Company"] = relationship()
    opportunity_score: Mapped["OpportunityScore"] = relationship()
