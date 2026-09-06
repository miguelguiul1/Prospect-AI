"""Modelos do domínio `scoring`.

`OpportunityScore` é relacionado a um `AuditSnapshot` específico — nunca
diretamente e de forma permanente a uma `Company` — porque a oportunidade
comercial muda a cada nova auditoria, e o histórico de como ela evoluiu
precisa ser preservado (arquitetura v0.2, seções 06 e 14; decisão reafirmada
em `docs/data-model.md`, Fase 3: "AuditSnapshot, WebsiteQuality,
OpportunityScore: relação 1:1 com uma execução, não com a empresa"). A Fase 4
implementa o cálculo; a Fase 0-3 só reservavam a estrutura.
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
from app.domains.evidence.enums import ConfidenceLevel

if TYPE_CHECKING:
    from app.domains.audit.models import AuditSnapshot


def _now() -> datetime:
    return datetime.now(timezone.utc)


# Versão da fórmula/metodologia de scoring — muda quando pesos, dimensões ou
# regras de classificação mudam de forma que o mesmo conjunto de evidências
# passaria a produzir um número diferente. Persistida em cada
# `OpportunityScore` para que scores antigos continuem interpretáveis mesmo
# depois de uma recalibração futura (ver docs/opportunity-scoring.md).
SCORING_VERSION = "v1"


class OpportunityTier(str, enum.Enum):
    """Classificação por faixa do `OpportunityScore.score` (0-100).

    Ampliado de 3 para 5 faixas na Fase 4 (a arquitetura v0.2 e o prompt da
    Fase 4 pedem granularidade maior que a do placeholder da Fase 0). Como
    nenhuma linha de `opportunity_scores` foi persistida com `tier` != NULL
    antes da Fase 4 (o cálculo nunca rodou), não há dado histórico com os
    3 valores antigos para migrar — apenas o enum em código muda.
    """

    HIGH = "high"
    MEDIUM_HIGH = "medium_high"
    MEDIUM = "medium"
    LOW = "low"
    VERY_LOW = "very_low"


class OpportunityScore(Base):
    """Opportunity Score: heurística determinística de priorização comercial.

    NÃO é uma probabilidade estatística de conversão, nem uma medida de
    faturamento/orçamento do prospect — é um número 0-100 que combina sinais
    públicos e observáveis (gap de website, qualidade técnica do site,
    presença digital, visibilidade, adequação de segmento, facilidade de
    contato) para ajudar a priorizar QUEM abordar primeiro. Ver
    `app.domains.scoring.scoring` para a fórmula e
    `docs/opportunity-scoring.md` para a metodologia completa.

    `breakdown` grava, por dimensão: valor bruto, peso, contribuição para o
    score final, uma razão textual curta e referências às `Evidence`/
    `WebsiteQuality` usadas — nunca só o número final, para manter a decisão
    auditável (mesmo espírito do Website Quality Score, Fase 3).

    Recalcular (`OpportunityScoringService.compute`) ATUALIZA a linha
    existente para o mesmo `audit_snapshot_id` (a unicidade abaixo impede uma
    segunda linha) em vez de criar uma nova — o histórico de como a empresa
    evoluiu já é preservado pela cadeia de `AuditSnapshot` (uma nova
    auditoria sempre gera um novo snapshot e, portanto, um novo score); um
    recompute sobre o MESMO snapshot só faz sentido quando a fórmula/versão
    muda, e nesse caso substituir o valor antigo (não duplicá-lo) é a leitura
    mais simples e honesta do que "o score deste snapshot" significa.
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
    confidence: Mapped[ConfidenceLevel | None] = mapped_column(
        SAEnum(ConfidenceLevel, native_enum=False, length=20), nullable=True
    )
    scoring_version: Mapped[str] = mapped_column(String(10), nullable=False, default=SCORING_VERSION)
    breakdown: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    recommended_product: Mapped[str | None] = mapped_column(String(120), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )

    audit_snapshot: Mapped["AuditSnapshot"] = relationship(back_populates="opportunity_score")
