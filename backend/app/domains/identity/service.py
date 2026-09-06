"""Orquestração do Identity Resolution: candidatos -> comparação -> decisão
-> registro auditável, e o utilitário de merge de duas `Company` já
existentes.

Duas operações distintas vivem aqui, de propósito:

- `resolve_for_discovery` / `record_resolution`: o caminho normal, chamado
  pela persistência do Discovery (`app.domains.discovery.persistence`) para
  decidir se uma fonte nova pertence a uma `Company` já conhecida. Nunca
  funde duas `Company` já existentes — na pior das hipóteses, cria uma
  `Company` nova.
- `merge_companies`: a operação mais arriscada (seção 13 do prompt da Fase
  2) — funde duas `Company` que já existem como registros separados.
  Só é chamada explicitamente (por um humano ou por um processo futuro de
  revisão), nunca automaticamente pelo fluxo de Discovery.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.domains.companies.models import Company, CompanyStatus
from app.domains.discovery.dto import DiscoveredCompany
from app.domains.evidence.enums import ConfidenceLevel
from app.domains.evidence.models import Evidence
from app.domains.identity.enums import MatchDecision
from app.domains.identity.matching import MatchResult, is_trusted_website, resolve
from app.domains.identity.models import CompanySource, DedupCandidate, DedupCandidateStatus, IdentityMergeLog
from app.domains.identity.profile import CompanyProfile, build_profile_from_company, build_profile_from_discovered

logger = get_logger(__name__)

CANDIDATE_QUERY_LIMIT = 50


@dataclass(frozen=True)
class IdentityResolution:
    """Resultado de `resolve_for_discovery`, pronto para a persistência do
    Discovery decidir o que fazer (reaproveitar uma `Company` ou criar uma
    nova) e depois registrar via `record_resolution`."""

    decision: MatchDecision
    confidence: ConfidenceLevel
    reasons: list[str]
    signals: dict
    matched_company: Company | None
    representative_company: Company | None


class IdentityResolutionService:
    def __init__(self, db: Session, *, settings: Settings | None = None) -> None:
        self._db = db
        self._settings = settings or get_settings()

    # -- Caminho normal: Discovery -> Identity Resolution --------------------

    def find_candidates(self, profile: CompanyProfile) -> list[Company]:
        """Pré-filtro (blocking) barato antes da comparação fina: nunca
        compara o candidato contra a base inteira. Une três conjuntos —
        telefone atual igual, site oficial atual igual, mesma região —
        porque cada um sozinho pode perder um caso real (ex.: telefone
        ausente, mas nome+região corroboram)."""
        candidate_ids: set[uuid.UUID] = set()

        if profile.phone:
            candidate_ids |= self._company_ids_with_current_value("phone", profile.phone)

        if profile.website and is_trusted_website(profile.website):
            candidate_ids |= self._company_ids_with_current_value("website", profile.website)

        if profile.region_id:
            rows = (
                self._db.query(Company.id)
                .filter(Company.region_id == profile.region_id)
                .limit(CANDIDATE_QUERY_LIMIT)
                .all()
            )
            candidate_ids |= {row[0] for row in rows}

        if not candidate_ids:
            return []

        return (
            self._db.query(Company)
            .filter(Company.id.in_(candidate_ids))
            .order_by(Company.created_at)
            .all()
        )

    def _company_ids_with_current_value(self, field_name: str, value: str) -> set[uuid.UUID]:
        rows = (
            self._db.query(Evidence.company_id)
            .filter(
                Evidence.field == field_name,
                Evidence.value == value,
                Evidence.superseded_by_id.is_(None),
            )
            .all()
        )
        return {row[0] for row in rows}

    def resolve_for_discovery(
        self, discovered: DiscoveredCompany, *, region_id: uuid.UUID | None
    ) -> IdentityResolution:
        candidate_profile = build_profile_from_discovered(discovered, region_id=region_id)
        candidates = self.find_candidates(candidate_profile)

        if not candidates:
            return IdentityResolution(
                MatchDecision.NO_MATCH,
                ConfidenceLevel.LOW,
                ["nenhuma empresa existente para comparar"],
                {},
                matched_company=None,
                representative_company=None,
            )

        evaluations: list[tuple[Company, MatchResult]] = [
            (company, resolve(candidate_profile, build_profile_from_company(self._db, company), settings=self._settings))
            for company in candidates
        ]

        matches = [(c, r) for c, r in evaluations if r.decision == MatchDecision.MATCH]

        if len(matches) == 1:
            company, result = matches[0]
            return IdentityResolution(
                result.decision, result.confidence, result.reasons, result.signals,
                matched_company=company, representative_company=company,
            )

        if len(matches) > 1:
            # Ambíguo: mais de uma empresa existente pareceu corresponder.
            # Nunca escolhemos uma arbitrariamente — vira INCONCLUSIVE.
            company, _ = max(matches, key=lambda cr: cr[1].signals.get("name_score") or 0)
            reasons = [f"{len(matches)} empresas existentes corresponderam — ambíguo, requer revisão"]
            return IdentityResolution(
                MatchDecision.INCONCLUSIVE, ConfidenceLevel.MEDIUM, reasons, {"ambiguous_match_count": len(matches)},
                matched_company=None, representative_company=company,
            )

        inconclusive = [(c, r) for c, r in evaluations if r.decision == MatchDecision.INCONCLUSIVE]
        if inconclusive:
            company, result = max(inconclusive, key=lambda cr: cr[1].signals.get("name_score") or 0)
        else:
            company, result = evaluations[0]

        return IdentityResolution(
            result.decision, result.confidence, result.reasons, result.signals,
            matched_company=None, representative_company=company,
        )

    def record_resolution(
        self,
        discovered: DiscoveredCompany,
        resolution: IdentityResolution,
        *,
        resulting_company: Company,
    ) -> DedupCandidate | None:
        """Grava a decisão em `DedupCandidate`, se houve algum candidato
        real para comparar (sem candidatos, não há o que auditar)."""
        if resolution.representative_company is None:
            return None

        status = (
            DedupCandidateStatus.PENDING_REVIEW
            if resolution.decision == MatchDecision.INCONCLUSIVE
            else DedupCandidateStatus.AUTO_RESOLVED
        )

        row = DedupCandidate(
            company_id=resolution.representative_company.id,
            resulting_company_id=resulting_company.id,
            source=discovered.source,
            external_id=discovered.external_id,
            decision=resolution.decision,
            confidence=resolution.confidence,
            reasons=resolution.reasons,
            signals=resolution.signals,
            status=status,
        )
        self._db.add(row)
        self._db.flush()

        logger.info(
            "identity_resolution_recorded",
            decision=resolution.decision.value,
            status=status.value,
            company_id=str(resolution.representative_company.id),
            resulting_company_id=str(resulting_company.id),
            source=discovered.source,
            external_id=discovered.external_id,
        )
        return row

    # -- Merge de duas Company já existentes (seções 13/14) ------------------

    def choose_canonical(self, company_a: Company, company_b: Company) -> tuple[Company, Company]:
        """Escolhe qual das duas `Company` permanece como canônica.

        Regra determinística (seção 14): mais `CompanySource` vinculadas
        vence primeiro (identidade mais corroborada entre fontes); empate
        é resolvido por mais `Evidence` (dado mais completo); empate
        seguinte por `created_at` mais antigo (registro mais estabelecido);
        e o desempate final, para nunca depender de ordem de leitura do
        banco, é o menor UUID.
        """
        source_count = {
            company_a.id: len(company_a.sources),
            company_b.id: len(company_b.sources),
        }
        if source_count[company_a.id] != source_count[company_b.id]:
            return (company_a, company_b) if source_count[company_a.id] > source_count[company_b.id] else (company_b, company_a)

        evidence_count = {
            company_a.id: len(company_a.evidences),
            company_b.id: len(company_b.evidences),
        }
        if evidence_count[company_a.id] != evidence_count[company_b.id]:
            return (company_a, company_b) if evidence_count[company_a.id] > evidence_count[company_b.id] else (company_b, company_a)

        if company_a.created_at != company_b.created_at:
            return (company_a, company_b) if company_a.created_at < company_b.created_at else (company_b, company_a)

        return (company_a, company_b) if str(company_a.id) < str(company_b.id) else (company_b, company_a)

    def merge_companies(
        self,
        *,
        company_a_id: uuid.UUID,
        company_b_id: uuid.UUID,
        reason: str,
        decided_by: str = "system_auto",
        signals: dict | None = None,
    ) -> Company:
        """Funde duas `Company` já existentes, preservando todo o histórico.

        Nunca apaga `CompanySource`/`Evidence` da empresa descartada — só
        reassocia (via os atributos de relationship, não a coluna de FK
        direto, para não disparar o cascade `delete-orphan` das
        relationships de `Company`). A empresa descartada é marcada
        `ARCHIVED`, nunca removida — preserva a possibilidade de auditar
        ou reverter a decisão depois (`IdentityMergeLog.reverted_at`).
        """
        if company_a_id == company_b_id:
            raise ValueError("Não é possível fundir uma Company com ela mesma.")

        company_a = self._db.get(Company, company_a_id)
        company_b = self._db.get(Company, company_b_id)
        if company_a is None or company_b is None:
            raise ValueError("Uma das Companies informadas não existe.")

        primary, duplicate = self.choose_canonical(company_a, company_b)

        for source in list(duplicate.sources):
            source.company = primary
        for evidence in list(duplicate.evidences):
            evidence.company = primary

        duplicate.status = CompanyStatus.ARCHIVED

        merge_log = IdentityMergeLog(
            primary_company_id=primary.id,
            merged_company_id=duplicate.id,
            reason=reason,
            signals=signals or {},
            decided_by=decided_by,
        )
        self._db.add(merge_log)
        self._db.flush()

        logger.info(
            "companies_merged",
            primary_company_id=str(primary.id),
            merged_company_id=str(duplicate.id),
            decided_by=decided_by,
        )
        return primary


__all__ = ["IdentityResolution", "IdentityResolutionService"]
