"""Modelos do domínio `crm` (Fase 7).

Decisões desta fase, todas herdadas da auditoria F7.0 (não reabertas sem
motivo técnico novo — Prompt 11, seções 5.4/7.1/7.3):

- Nenhuma tabela `Lead` separada de `Opportunity` — o gradiente "frio até
  fechado" já é `PipelineStage`.
- Nenhuma tabela `Pipeline` contêiner — um único conjunto de etapas globais
  e ordenadas é suficiente; ver `PipelineStage`.
- Nenhuma tabela `OpportunityStageHistory` separada — uma mudança de etapa
  já é uma `Activity(type=STAGE_CHANGE)`, a mesma tabela usada para todo o
  resto da timeline (ver `Activity`).
- `Opportunity` referencia `Company` só por `company_id` — nunca copia
  nome/endereço/telefone/website/categoria (Prompt 11, seção 5.1).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, Uuid
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.domains.crm.enums import (
    ActivityStatus,
    ActivityType,
    ContactValidationStatus,
    OpportunityPriority,
    OpportunityStatus,
)

if TYPE_CHECKING:
    from app.domains.auth.models import User
    from app.domains.companies.models import Company


def _now() -> datetime:
    return datetime.now(timezone.utc)


class PipelineStage(Base):
    """Etapa global e ordenada do funil comercial.

    `key` é o identificador estável usado por código (nunca traduzido/
    renomeável); `name` é o rótulo exibido, editável sem quebrar nenhuma
    lógica. `is_won`/`is_lost` marcam as etapas terminais — usadas para
    decidir automaticamente `Opportunity.status` quando a etapa muda (ver
    `app.domains.crm.service.OpportunityService.change_stage`).
    """

    __tablename__ = "pipeline_stages"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    key: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    order: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    is_won: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_lost: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class Opportunity(Base):
    """Contexto comercial de uma `Company` (Fase 7).

    Uma `Company` pode ter várias `Opportunity` ao longo do tempo (auditoria
    F7.0, seção 7), mas nunca duas ABERTAS simultaneamente — o índice único
    parcial abaixo (`uq_opportunities_company_open`) garante isso no banco,
    não só na aplicação, para que duas requisições concorrentes de "criar
    oportunidade" não produzam duplicata (Prompt 11, seções 6 e 24):
    `OpportunityService.create_or_get` trata a violação dessa constraint
    como "já existe, devolva a existente" em vez de deixar o erro subir.
    """

    __tablename__ = "opportunities"
    # NOTA: SQLAlchemy `Enum(EnumClass)` persiste, por padrão, o NOME do
    # membro do enum (ex.: "OPEN"), não `.value` ("open") — por isso o
    # predicado do índice parcial abaixo compara contra 'OPEN' em
    # maiúsculas. Confirmado contra o comportamento já usado nas migrations
    # anteriores (`0005_...`: `sa.Enum('COMPLETED', 'FAILED', ...)`).
    __table_args__ = (
        Index(
            "uq_opportunities_company_open",
            "company_id",
            unique=True,
            sqlite_where="status = 'OPEN'",
            postgresql_where="status = 'OPEN'",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"), nullable=False, index=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    stage_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pipeline_stages.id"), nullable=False, index=True)

    status: Mapped[OpportunityStatus] = mapped_column(
        SAEnum(OpportunityStatus, native_enum=False, length=20),
        nullable=False,
        default=OpportunityStatus.OPEN,
    )
    priority: Mapped[OpportunityPriority] = mapped_column(
        SAEnum(OpportunityPriority, native_enum=False, length=20),
        nullable=False,
        default=OpportunityPriority.MEDIUM,
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    company: Mapped["Company"] = relationship()
    owner: Mapped["User"] = relationship()
    stage: Mapped["PipelineStage"] = relationship()


class Contact(Base):
    """Uma pessoa relacionada a uma `Company` (Fase 7).

    NUNCA criado automaticamente a partir de dados da Discovery — telefone/
    site em nível de empresa não são "um contato pessoal válido" (Prompt 11,
    seção 8.2; auditoria F7.0, seção 9). `source` registra a origem real
    ("manual", "imported", "form") para essa distinção permanecer visível.
    """

    __tablename__ = "contacts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"), nullable=False, index=True)

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str | None] = mapped_column(String(120), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source: Mapped[str] = mapped_column(String(30), nullable=False, default="manual")
    validation_status: Mapped[ContactValidationStatus] = mapped_column(
        SAEnum(ContactValidationStatus, native_enum=False, length=20),
        nullable=False,
        default=ContactValidationStatus.UNVERIFIED,
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )

    company: Mapped["Company"] = relationship()


class Activity(Base):
    """Entrada única de timeline de uma `Opportunity` (Fase 7).

    Uma única tabela com `type` cobre nota/tarefa/ligação/reunião/e-mail/
    WhatsApp/outreach/mudança de etapa/mudança de responsável/evento de
    sistema — mesmo padrão de "uma tabela, um campo de discriminação" já
    usado com sucesso em `DedupCandidate` (Fase 2). `status`/`due_at`/
    `completed_at` só têm sentido quando `type == TASK`; permanecem `None`
    nos demais tipos. `context` guarda detalhes específicos do tipo (ex.:
    `{"from_stage": ..., "to_stage": ...}` em `STAGE_CHANGE`) sem exigir
    colunas específicas por tipo.
    """

    __tablename__ = "activities"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("opportunities.id"), nullable=False, index=True
    )

    type: Mapped[ActivityType] = mapped_column(SAEnum(ActivityType, native_enum=False, length=24), nullable=False)
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Texto puro — nunca HTML (ver app.domains.crm.schemas: nenhum campo
    # deste domínio aceita markup, e nenhum renderer do frontend usa
    # dangerouslySetInnerHTML para exibi-lo).
    description: Mapped[str | None] = mapped_column(String(4000), nullable=True)
    status: Mapped[ActivityStatus | None] = mapped_column(
        SAEnum(ActivityStatus, native_enum=False, length=10), nullable=True
    )
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    context: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)

    opportunity: Mapped["Opportunity"] = relationship()
