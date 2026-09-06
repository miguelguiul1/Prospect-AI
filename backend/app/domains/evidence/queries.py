"""Leitura do "valor atual" de um campo a partir do histórico de `Evidence`.

Importante: isto NÃO é a resolução de conflitos ponderada por confiança e
recência que a arquitetura v0.2 reserva para a Fase 3 (Digital Auditor) —
aquela precisa decidir entre valores CONCORRENTES de fontes diferentes,
com pesos de confiança. Esta função é mais simples e mais restrita: como
`app.domains.discovery.persistence` mantém no máximo uma `Evidence` não
superada por `(company_id, field)` a qualquer momento (cada novo valor
supera o anterior via `Evidence.mark_superseded_by`), sempre existe no
máximo uma linha "atual" para buscar — não há empate para resolver.

Usado tanto pela persistência do Discovery quanto pelo Identity Resolution
(Fase 2), que precisa saber "qual é o telefone/endereço/site conhecido
desta empresa" para comparar contra um novo candidato.
"""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.domains.evidence.models import Evidence


def get_current_evidence(db: Session, company_id: uuid.UUID, field: str) -> Evidence | None:
    return (
        db.query(Evidence)
        .filter(
            Evidence.company_id == company_id,
            Evidence.field == field,
            Evidence.superseded_by_id.is_(None),
        )
        .order_by(Evidence.collected_at.desc())
        .first()
    )


def get_current_value(db: Session, company_id: uuid.UUID, field: str) -> str | None:
    evidence = get_current_evidence(db, company_id, field)
    return evidence.value if evidence is not None else None
