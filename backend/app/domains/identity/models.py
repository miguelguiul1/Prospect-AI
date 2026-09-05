"""Modelos do domínio `identity`.

`CompanySource` é a peça central da correção arquitetural v0.1 -> v0.2:
nenhum identificador de fonte externa (place_id do Google, osm_id, CNPJ,
ID de conta do Instagram, ...) é gravado em `Company`. Toda fonte externa
aponta para uma `Company` através de uma linha aqui — uma empresa pode (e
deve, com o tempo) ter várias.

`IdentityMergeLog` registra toda fusão (ou reversão de fusão) de identidade
entre duas `Company`, para que seja possível investigar depois por que duas
empresas foram consideradas a mesma. Nenhuma lógica de fusão automática é
implementada nesta fase — a tabela existe para as fases futuras gravarem
nela.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.domains.evidence.enums import ConfidenceLevel

if TYPE_CHECKING:
    from app.domains.companies.models import Company


def _now() -> datetime:
    return datetime.now(timezone.utc)


class CompanySource(Base):
    """Vínculo entre uma `Company` interna e sua representação em uma fonte
    externa específica. `(source, external_id)` é único: é isso que torna
    reprocessar a mesma fonte idempotente por construção.
    """

    __tablename__ = "company_sources"
    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_company_sources_source_external_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"), nullable=False, index=True)

    # String livre (não Enum de banco) de propósito: novas fontes (uma nova
    # rede social, um novo provedor de CNPJ) devem poder ser adicionadas sem
    # exigir uma migration de schema. Ver docs/data-model.md.
    source: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    confidence: Mapped[ConfidenceLevel] = mapped_column(
        SAEnum(ConfidenceLevel, native_enum=False, length=20), nullable=False
    )
    raw_reference: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )

    company: Mapped["Company"] = relationship(back_populates="sources")


class IdentityMergeLog(Base):
    """Registro histórico de fusão (ou reversão) entre dois `Company`.

    `merged_company_id` é a empresa que deixou de ser usada como identidade
    principal; `primary_company_id` é a que permanece. `reverted_at` marcado
    indica que uma fusão foi posteriormente desfeita por revisão humana —
    a linha nunca é apagada, só marcada.
    """

    __tablename__ = "identity_merge_logs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    primary_company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id"), nullable=False, index=True
    )
    merged_company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id"), nullable=False, index=True
    )

    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    signals: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    decided_by: Mapped[str] = mapped_column(String(120), nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    reverted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
