"""Modelo do domínio `outreach` (Fase 7) — Assisted Outreach (Nível 1).

Uma linha por sugestão gerada — nunca sobrescrita (mesmo padrão append-only
de `SalesBrief`): editar o rascunho ou pedir uma nova sugestão sempre altera
esta linha em memória antes de `SENT_MANUALLY`, mas o histórico de
tentativas de uma `Opportunity` continua completo porque cada geração é uma
nova linha. `status` NUNCA chega a `SENT_MANUALLY` automaticamente — só uma
confirmação explícita do usuário faz essa transição (Prompt 11, seção
18.2: "Não registre como enviado automaticamente").
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Uuid
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.domains.outreach.enums import OutreachChannel, OutreachStatus

if TYPE_CHECKING:
    from app.domains.crm.models import Contact, Opportunity


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Outreach(Base):
    __tablename__ = "outreach_messages"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    opportunity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("opportunities.id"), nullable=False, index=True)
    contact_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("contacts.id"), nullable=True, index=True)

    channel: Mapped[OutreachChannel] = mapped_column(SAEnum(OutreachChannel, native_enum=False, length=20), nullable=False)
    status: Mapped[OutreachStatus] = mapped_column(
        SAEnum(OutreachStatus, native_enum=False, length=20), nullable=False, default=OutreachStatus.DRAFT
    )

    subject: Mapped[str | None] = mapped_column(String(300), nullable=True)
    message: Mapped[str | None] = mapped_column(String(4000), nullable=True)
    # Por que a IA sugeriu este texto — transparência de grounding (Prompt
    # 11, seção 19.3), nunca exibido como parte da mensagem em si.
    rationale: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    evidence_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    generated_by_ai: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    provider: Mapped[str | None] = mapped_column(String(40), nullable=True)
    model: Mapped[str | None] = mapped_column(String(80), nullable=True)
    prompt_version: Mapped[str] = mapped_column(String(10), nullable=False, default="v1")
    duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )

    opportunity: Mapped["Opportunity"] = relationship()
    contact: Mapped["Contact | None"] = relationship()
