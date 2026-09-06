"""Orquestração do Opportunity Score:

Company -> última AuditSnapshot -> Evidence atual + Website Quality ->
ScoringContext -> compute_opportunity_score -> OpportunityScore persistido.

Nunca coleta evidência nova — só lê o que Discovery (Fase 1), Identity
Resolution (Fase 2) e Digital Audit (Fase 3) já gravaram no Evidence Layer.
Nenhuma IA participa: ver `app.domains.scoring.scoring` para a fórmula.
"""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.domains.audit.models import AuditSnapshot
from app.domains.companies.models import Company
from app.domains.evidence.queries import get_current_evidence
from app.domains.scoring.models import SCORING_VERSION, OpportunityScore, OpportunityTier
from app.domains.scoring.scoring import EvidenceRef, ScoringContext, compute_opportunity_score


def _ref(db: Session, company_id: uuid.UUID, field: str) -> EvidenceRef | None:
    evidence = get_current_evidence(db, company_id, field)
    if evidence is None:
        return None
    return EvidenceRef(field=field, value=evidence.value, evidence_id=str(evidence.id))


class OpportunityScoringService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def _latest_audit_snapshot(self, company_id: uuid.UUID) -> AuditSnapshot | None:
        return (
            self._db.query(AuditSnapshot)
            .filter(AuditSnapshot.company_id == company_id)
            .order_by(AuditSnapshot.created_at.desc())
            .first()
        )

    def build_context(self, company: Company, snapshot: AuditSnapshot) -> ScoringContext:
        return ScoringContext(
            site_state=snapshot.site_state,
            website_quality=snapshot.website_quality,
            website_value=_ref(self._db, company.id, "website"),
            category_slug=company.category.slug if company.category else None,
            rating=_ref(self._db, company.id, "rating"),
            review_count=_ref(self._db, company.id, "review_count"),
            phone=_ref(self._db, company.id, "phone"),
            address=_ref(self._db, company.id, "address"),
            website_contact_available=_ref(self._db, company.id, "website_contact_available"),
        )

    def compute(self, company_id: uuid.UUID) -> OpportunityScore:
        """Calcula (ou recalcula) o Opportunity Score para a auditoria mais
        recente da empresa. Levanta `ValueError` se a empresa não existe ou
        se nenhuma `AuditSnapshot` foi executada ainda — o Opportunity Score
        depende de uma auditoria (Fase 3) já ter rodado ao menos uma vez."""
        company = self._db.get(Company, company_id)
        if company is None:
            raise LookupError(f"Company {company_id} não encontrada")

        snapshot = self._latest_audit_snapshot(company_id)
        if snapshot is None:
            raise ValueError(
                f"Company {company_id} não tem nenhuma auditoria (AuditSnapshot) executada ainda — "
                "rode POST /api/audit/{company_id} antes de calcular o Opportunity Score."
            )
        if snapshot.site_state is None:
            raise ValueError(
                f"AuditSnapshot {snapshot.id} ainda não foi concluído (site_state vazio) — "
                "aguarde a auditoria terminar antes de calcular o Opportunity Score."
            )

        ctx = self.build_context(company, snapshot)
        result = compute_opportunity_score(ctx)

        existing = (
            self._db.query(OpportunityScore)
            .filter(OpportunityScore.audit_snapshot_id == snapshot.id)
            .one_or_none()
        )

        tier = OpportunityTier(result.tier) if result.tier is not None else None

        if existing is not None:
            existing.score = result.score
            existing.tier = tier
            existing.confidence = result.confidence
            existing.scoring_version = SCORING_VERSION
            existing.breakdown = result.breakdown
            self._db.flush()
            return existing

        opportunity_score = OpportunityScore(
            audit_snapshot_id=snapshot.id,
            score=result.score,
            tier=tier,
            confidence=result.confidence,
            scoring_version=SCORING_VERSION,
            breakdown=result.breakdown,
        )
        self._db.add(opportunity_score)
        self._db.flush()
        return opportunity_score

    def get_latest(self, company_id: uuid.UUID) -> OpportunityScore | None:
        return (
            self._db.query(OpportunityScore)
            .join(AuditSnapshot, OpportunityScore.audit_snapshot_id == AuditSnapshot.id)
            .filter(AuditSnapshot.company_id == company_id)
            .order_by(OpportunityScore.created_at.desc())
            .first()
        )


__all__ = ["OpportunityScoringService"]
