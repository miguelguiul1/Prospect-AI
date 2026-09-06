"""Escolha do candidato de website a auditar, a partir do `Evidence` já
existente de uma `Company` (produzido pelo Discovery/Identity Resolution
— Fases 1/2). O Digital Audit não descobre um novo website aqui; ele audita
o que já foi observado.

Nunca trata Instagram/Facebook/TikTok/WhatsApp/Linktree/marketplaces/
diretórios/mapas como website oficial (arquitetura Fase 3, seção 3) —
reaproveita `is_trusted_website`, já usado pelo Identity Resolution (Fase 2)
para exatamente essa distinção.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.domains.discovery.normalization import extract_hostname, is_trusted_website, normalize_url
from app.domains.evidence.models import Evidence

# Quantas observações recentes do campo "website" olhamos para detectar
# desacordo entre fontes — não a história inteira (que pode ser longa),
# só o suficiente para notar se o valor tem oscilado entre hostnames
# diferentes reportados por fontes diferentes.
_HISTORY_LOOKBACK = 5


class WebsiteCandidateStatus:
    """Não é um Enum de banco — só rótulos internos usados por
    `DigitalAuditService` para decidir o `DataState` inicial antes de
    qualquer tentativa de rede."""

    FOUND = "found"
    NONE = "none"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True)
class WebsiteCandidate:
    status: str
    url: str | None
    hostname: str | None
    source: str | None
    evidence_id: uuid.UUID | None
    note: str | None = None


def select_website_candidate(db: Session, company_id: uuid.UUID) -> WebsiteCandidate:
    history = (
        db.query(Evidence)
        .filter(Evidence.company_id == company_id, Evidence.field == "website")
        .order_by(Evidence.collected_at.desc())
        .limit(_HISTORY_LOOKBACK)
        .all()
    )

    current = next((row for row in history if row.superseded_by_id is None), None)

    if current is None or not current.value:
        return WebsiteCandidate(
            status=WebsiteCandidateStatus.NONE, url=None, hostname=None, source=None, evidence_id=None
        )

    normalized = normalize_url(current.value)
    if normalized is None or not is_trusted_website(normalized):
        return WebsiteCandidate(
            status=WebsiteCandidateStatus.NONE,
            url=None,
            hostname=None,
            source=current.source,
            evidence_id=current.id,
            note="único candidato conhecido não é um domínio de site oficial (rede social/agregador).",
        )

    trusted_hostnames = {
        extract_hostname(normalize_url(row.value))
        for row in history
        if row.value and normalize_url(row.value) and is_trusted_website(row.value)
    }

    if len(trusted_hostnames) > 1:
        return WebsiteCandidate(
            status=WebsiteCandidateStatus.AMBIGUOUS,
            url=normalized,
            hostname=extract_hostname(normalized),
            source=current.source,
            evidence_id=current.id,
            note=(
                f"fontes diferentes reportaram hostnames de site oficial diferentes nas últimas "
                f"observações: {sorted(trusted_hostnames)}."
            ),
        )

    return WebsiteCandidate(
        status=WebsiteCandidateStatus.FOUND,
        url=normalized,
        hostname=extract_hostname(normalized),
        source=current.source,
        evidence_id=current.id,
    )
