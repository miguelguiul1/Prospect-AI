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

from app.domains.evidence.enums import ConfidenceLevel, DataState, EvidenceMethod
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


def upsert_evidence(
    db: Session,
    *,
    company_id: uuid.UUID,
    field: str,
    value: str | None,
    state: DataState,
    source: str,
    method: EvidenceMethod,
    confidence: ConfidenceLevel,
    source_url: str | None = None,
    audit_snapshot_id: uuid.UUID | None = None,
    match_score: float | None = None,
    raw_reference: dict | None = None,
) -> Evidence:
    """Versão general-purpose do padrão append-only já usado por
    `app.domains.discovery.persistence` desde a Fase 1: só grava uma nova
    `Evidence` quando `value`/`state` realmente mudaram desde a última
    observação não superada; caso contrário, devolve a existente sem criar
    uma linha redundante. A antiga, quando superada, nunca é editada — só
    ganha `superseded_by_id` apontando para a nova (arquitetura v0.2, seção
    08).

    `app.domains.discovery.persistence._upsert_evidence` continua existindo
    como está (mais simples, hardcoded para o caso do Discovery) — esta
    função generalizada é a que a Fase 3 (Digital Audit) usa, por precisar
    de `state` variável (nem todo sinal de auditoria é `CONFIRMED`) e de
    vínculo com um `AuditSnapshot`.
    """
    latest = get_current_evidence(db, company_id, field)

    if latest is not None and latest.value == value and latest.state == state:
        return latest

    new_evidence = Evidence(
        company_id=company_id,
        audit_snapshot_id=audit_snapshot_id,
        field=field,
        value=value,
        state=state,
        source=source,
        source_url=source_url,
        method=method,
        confidence=confidence,
        match_score=match_score,
        raw_reference=raw_reference,
    )
    db.add(new_evidence)
    db.flush()

    if latest is not None:
        latest.mark_superseded_by(new_evidence)

    return new_evidence
