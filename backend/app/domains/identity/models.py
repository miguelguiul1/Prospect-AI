"""Modelos do domínio `identity`.

`CompanySource` é a peça central da correção arquitetural v0.1 -> v0.2:
nenhum identificador de fonte externa (place_id do Google, osm_id, CNPJ,
ID de conta do Instagram, ...) é gravado em `Company`. Toda fonte externa
aponta para uma `Company` através de uma linha aqui — uma empresa pode (e
deve, com o tempo) ter várias.

`IdentityMergeLog` registra toda fusão (ou reversão de fusão) de identidade
entre duas `Company`, para que seja possível investigar depois por que duas
empresas foram consideradas a mesma.

`DedupCandidate` (Fase 2) é o registro auditável de toda decisão não
trivial do Identity Resolution — foi anunciado como pendente em
docs/data-model.md desde a Fase 0 ("será adicionada quando a Identity
Resolution for implementada"). Cobre tanto os casos confiantes
(`MATCH`/`NO_MATCH`, `status=auto_resolved`) quanto os ambíguos
(`INCONCLUSIVE`, `status=pending_review`) — uma única tabela em vez de duas
(log de auditoria + fila de revisão), porque toda decisão de revisão
humana já é, por definição, uma decisão auditada. Ver
docs/identity-resolution.md.
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, Float
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.domains.evidence.enums import ConfidenceLevel
from app.domains.identity.enums import MatchDecision

if TYPE_CHECKING:
    from app.domains.companies.models import Company


def _now() -> datetime:
    return datetime.now(timezone.utc)


class DedupCandidateStatus(str, enum.Enum):
    """Ciclo de vida de uma decisão de identidade registrada.

    `AUTO_RESOLVED` cobre tanto MATCH quanto NO_MATCH confiantes — nenhum
    dos dois precisa de revisão humana. `PENDING_REVIEW` é exclusivo de
    decisões `INCONCLUSIVE`. `CONFIRMED_SAME`/`CONFIRMED_DIFFERENT` existem
    para uma revisão humana futura (Fase 5/dashboard) marcar o desfecho —
    nenhum código desta fase os atribui.
    """

    AUTO_RESOLVED = "auto_resolved"
    PENDING_REVIEW = "pending_review"
    CONFIRMED_SAME = "confirmed_same"
    CONFIRMED_DIFFERENT = "confirmed_different"


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

    # Coordenadas reportadas por ESTA fonte (Fase 2) — usadas como sinal de
    # apoio no Identity Resolution. Ver app/domains/identity/profile.py.
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)

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


class DedupCandidate(Base):
    """Registro auditável de uma decisão de Identity Resolution (Fase 2).

    `company_id` é a `Company` já existente que foi comparada contra o novo
    candidato; `resulting_company_id` é a `Company` à qual a fonte do
    candidato acabou associada — igual a `company_id` quando `decision`
    é `MATCH`, ou uma `Company` recém-criada quando é `NO_MATCH`/
    `INCONCLUSIVE` (arquitetura Fase 2, seção 9: na dúvida, mantém-se
    separado). `source`/`external_id` identificam a observação nova que
    disparou a comparação — nunca uma segunda `Company` já persistida
    (para esse caso, ver `IdentityMergeLog`).
    """

    __tablename__ = "dedup_candidates"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)

    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"), nullable=False, index=True)
    resulting_company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id"), nullable=False, index=True
    )

    source: Mapped[str] = mapped_column(String(60), nullable=False)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)

    decision: Mapped[MatchDecision] = mapped_column(
        SAEnum(MatchDecision, native_enum=False, length=20), nullable=False
    )
    confidence: Mapped[ConfidenceLevel] = mapped_column(
        SAEnum(ConfidenceLevel, native_enum=False, length=20), nullable=False
    )
    reasons: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    signals: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    status: Mapped[DedupCandidateStatus] = mapped_column(
        SAEnum(DedupCandidateStatus, native_enum=False, length=24),
        nullable=False,
        default=DedupCandidateStatus.AUTO_RESOLVED,
    )
    decided_by: Mapped[str] = mapped_column(String(120), nullable=False, default="system_auto")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
