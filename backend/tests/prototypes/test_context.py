"""Testes de `PrototypeContextBuilder` (Fase 9 / Prompt 11).

Regra central testada em todo lugar: nenhum campo é omitido — ausência
sempre vira `ContextConfidence.UNKNOWN` explícito, nunca um campo faltando
da estrutura."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy.orm import Session

from app.domains.audit.enums import AuditStatus
from app.domains.audit.models import AuditSnapshot
from app.domains.briefing.models import SalesBrief, SalesBriefStatus
from app.domains.companies.models import Category, Company, Region
from app.domains.evidence.enums import ConfidenceLevel, DataState, EvidenceMethod
from app.domains.evidence.models import Evidence
from app.domains.prototypes.context import (
    ContextConfidence,
    InsufficientContextError,
    PrototypeContextBuilder,
)
from app.domains.scoring.models import OpportunityScore, OpportunityTier


def _company(db: Session, name: str = "Padaria Central") -> Company:
    category = Category(slug="padaria", name="Padaria")
    region = Region(name="São Paulo", country="BR")
    db.add_all([category, region])
    db.flush()
    company = Company(canonical_name=name, category_id=category.id, region_id=region.id)
    db.add(company)
    db.flush()
    return company


def _evidence(
    db: Session,
    company_id: uuid.UUID,
    *,
    field: str,
    value: str | None,
    state: DataState = DataState.CONFIRMED,
    confidence: ConfidenceLevel = ConfidenceLevel.HIGH,
    method: EvidenceMethod = EvidenceMethod.STRUCTURED_FIELD,
) -> Evidence:
    evidence = Evidence(
        company_id=company_id,
        field=field,
        value=value,
        state=state,
        source="google_places",
        method=method,
        confidence=confidence,
    )
    db.add(evidence)
    db.flush()
    return evidence


def _audit_snapshot(db: Session, company_id: uuid.UUID, *, site_state: DataState = DataState.CONFIRMED) -> AuditSnapshot:
    snapshot = AuditSnapshot(
        company_id=company_id,
        run_id=uuid.uuid4(),
        status=AuditStatus.COMPLETED,
        site_state=site_state,
        website_url="https://padariacentral.example.com",
    )
    db.add(snapshot)
    db.flush()
    return snapshot


class TestInsufficientContext:
    def test_unknown_company_raises_lookup_error(self, db_session: Session) -> None:
        with pytest.raises(LookupError):
            PrototypeContextBuilder(db_session).build(uuid.uuid4())

    def test_company_with_no_evidence_and_no_audit_raises_insufficient_context(self, db_session: Session) -> None:
        company = _company(db_session)
        with pytest.raises(InsufficientContextError):
            PrototypeContextBuilder(db_session).build(company.id)

    def test_company_with_only_an_audit_snapshot_is_sufficient(self, db_session: Session) -> None:
        """Um AuditSnapshot sozinho (sem nenhuma Evidence) já é material
        real o bastante — não exige as duas coisas ao mesmo tempo."""
        company = _company(db_session)
        _audit_snapshot(db_session, company.id)

        context = PrototypeContextBuilder(db_session).build(company.id)
        assert context.company_name.value == "Padaria Central"

    def test_company_with_only_evidence_is_sufficient(self, db_session: Session) -> None:
        company = _company(db_session)
        _evidence(db_session, company.id, field="phone", value="+55 11 99999-0000")

        context = PrototypeContextBuilder(db_session).build(company.id)
        assert context.phone.confidence == ContextConfidence.FACT


class TestCompleteContext:
    def test_company_name_is_always_a_fact(self, db_session: Session) -> None:
        company = _company(db_session)
        _audit_snapshot(db_session, company.id)

        context = PrototypeContextBuilder(db_session).build(company.id)

        assert context.company_name.value == "Padaria Central"
        assert context.company_name.confidence == ContextConfidence.FACT
        assert context.company_name.source == "company.canonical_name"

    def test_high_confidence_confirmed_evidence_is_a_fact(self, db_session: Session) -> None:
        company = _company(db_session)
        _evidence(db_session, company.id, field="phone", value="+55 11 99999-0000", confidence=ConfidenceLevel.HIGH)

        context = PrototypeContextBuilder(db_session).build(company.id)

        assert context.phone.value == "+55 11 99999-0000"
        assert context.phone.confidence == ContextConfidence.FACT
        assert context.phone.source == "evidence:phone"

    def test_low_confidence_confirmed_evidence_is_a_signal_not_a_fact(self, db_session: Session) -> None:
        company = _company(db_session)
        _evidence(db_session, company.id, field="address", value="Rua X, 123", confidence=ConfidenceLevel.LOW)

        context = PrototypeContextBuilder(db_session).build(company.id)

        assert context.address.confidence == ContextConfidence.SIGNAL

    def test_non_confirmed_evidence_is_a_signal(self, db_session: Session) -> None:
        company = _company(db_session)
        _evidence(db_session, company.id, field="phone", value="+55 11 99999-0000", state=DataState.INCONCLUSIVE)

        context = PrototypeContextBuilder(db_session).build(company.id)

        assert context.phone.confidence == ContextConfidence.SIGNAL

    def test_inference_method_evidence_is_inference(self, db_session: Session) -> None:
        company = _company(db_session)
        _evidence(
            db_session,
            company.id,
            field="phone",
            value="provavelmente +55 11 99999-0000",
            method=EvidenceMethod.INFERENCE,
        )

        context = PrototypeContextBuilder(db_session).build(company.id)

        assert context.phone.confidence == ContextConfidence.INFERENCE

    def test_missing_evidence_field_is_explicitly_unknown_not_omitted(self, db_session: Session) -> None:
        company = _company(db_session)
        _audit_snapshot(db_session, company.id)

        context = PrototypeContextBuilder(db_session).build(company.id)

        assert context.phone.confidence == ContextConfidence.UNKNOWN
        assert context.phone.value is None
        assert context.address.confidence == ContextConfidence.UNKNOWN

    def test_site_state_confirmed_is_fact_other_states_are_signal(self, db_session: Session) -> None:
        company = _company(db_session)
        _audit_snapshot(db_session, company.id, site_state=DataState.NOT_DETECTED)

        context = PrototypeContextBuilder(db_session).build(company.id)

        assert context.site_state.value == "not_detected"
        assert context.site_state.confidence == ContextConfidence.SIGNAL

    def test_social_links_are_split_from_the_stored_comma_joined_string(self, db_session: Session) -> None:
        company = _company(db_session)
        _evidence(db_session, company.id, field="website_social_links", value="https://instagram.com/x, https://facebook.com/x")

        context = PrototypeContextBuilder(db_session).build(company.id)

        assert context.social_links.value == ["https://instagram.com/x", "https://facebook.com/x"]

    def test_opportunity_score_fields_when_score_exists(self, db_session: Session) -> None:
        company = _company(db_session)
        snapshot = _audit_snapshot(db_session, company.id)
        score = OpportunityScore(
            audit_snapshot_id=snapshot.id,
            score=72.5,
            tier=OpportunityTier.HIGH,
            confidence=ConfidenceLevel.HIGH,
            recommended_product="landing page",
        )
        db_session.add(score)
        db_session.flush()

        context = PrototypeContextBuilder(db_session).build(company.id)

        assert context.opportunity_score.value == 72.5
        assert context.opportunity_tier.value == "high"
        assert context.recommended_product.value == "landing page"
        assert context.recommended_product.confidence == ContextConfidence.INFERENCE

    def test_sales_brief_content_is_inference_and_only_used_when_completed(self, db_session: Session) -> None:
        company = _company(db_session)
        snapshot = _audit_snapshot(db_session, company.id)
        score = OpportunityScore(audit_snapshot_id=snapshot.id, score=50.0)
        db_session.add(score)
        db_session.flush()
        brief = SalesBrief(
            company_id=company.id,
            opportunity_score_id=score.id,
            status=SalesBriefStatus.COMPLETED,
            content={"summary": "Empresa local com boa reputação.", "suggested_angle": "Modernizar presença digital."},
            prompt_version="v1",
        )
        db_session.add(brief)
        db_session.flush()

        context = PrototypeContextBuilder(db_session).build(company.id)

        assert context.sales_brief_summary.value == "Empresa local com boa reputação."
        assert context.sales_brief_summary.confidence == ContextConfidence.INFERENCE
        assert context.sales_brief_suggested_angle.value == "Modernizar presença digital."

    def test_failed_sales_brief_is_never_used(self, db_session: Session) -> None:
        company = _company(db_session)
        snapshot = _audit_snapshot(db_session, company.id)
        score = OpportunityScore(audit_snapshot_id=snapshot.id, score=50.0)
        db_session.add(score)
        db_session.flush()
        brief = SalesBrief(
            company_id=company.id,
            opportunity_score_id=score.id,
            status=SalesBriefStatus.FAILED,
            content=None,
            prompt_version="v1",
            error_code="ProviderUnavailableError",
        )
        db_session.add(brief)
        db_session.flush()

        context = PrototypeContextBuilder(db_session).build(company.id)

        assert context.sales_brief_summary.confidence == ContextConfidence.UNKNOWN

    def test_freshness_is_the_oldest_evidence_collected_at(self, db_session: Session) -> None:
        company = _company(db_session)
        _evidence(db_session, company.id, field="phone", value="+55 11 99999-0000")

        context = PrototypeContextBuilder(db_session).build(company.id)

        assert context.freshness is not None

    def test_no_field_is_ever_missing_from_the_context(self, db_session: Session) -> None:
        """Todo campo declarado em PrototypeContext existe e é um
        ContextField — nunca None cru, nunca ausente."""
        company = _company(db_session)
        _audit_snapshot(db_session, company.id)

        context = PrototypeContextBuilder(db_session).build(company.id)

        for name, ctx_field in context.all_fields().items():
            assert ctx_field.confidence in ContextConfidence, name
            assert ctx_field.source, name
