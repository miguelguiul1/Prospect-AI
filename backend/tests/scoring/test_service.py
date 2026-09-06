"""Testes de integração de `OpportunityScoringService` contra o banco real
de teste (SQLite via `db_session`) — sem rede, sem IA."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy.orm import Session

from app.domains.audit.enums import AuditStatus
from app.domains.audit.models import AuditSnapshot, WebsiteQuality
from app.domains.companies.models import Category, Company
from app.domains.evidence.enums import ConfidenceLevel, DataState, EvidenceMethod
from app.domains.evidence.models import Evidence
from app.domains.scoring.models import SCORING_VERSION, OpportunityScore
from app.domains.scoring.service import OpportunityScoringService


def _company(db: Session, *, category_slug: str | None = None) -> Company:
    category = None
    if category_slug:
        category = Category(slug=category_slug, name=category_slug.capitalize())
        db.add(category)
        db.flush()
    company = Company(canonical_name="Barbearia Exemplo", category_id=category.id if category else None)
    db.add(company)
    db.flush()
    return company


def _audit_snapshot(db: Session, company: Company, *, site_state: DataState, quality_score: float | None = None) -> AuditSnapshot:
    snapshot = AuditSnapshot(company_id=company.id, run_id=uuid.uuid4(), status=AuditStatus.COMPLETED, site_state=site_state)
    db.add(snapshot)
    db.flush()
    if quality_score is not None:
        quality = WebsiteQuality(audit_snapshot_id=snapshot.id, score=quality_score, confidence=ConfidenceLevel.HIGH)
        db.add(quality)
        db.flush()
    return snapshot


def _evidence(db: Session, company: Company, field: str, value: str) -> None:
    db.add(
        Evidence(
            company_id=company.id, field=field, value=value, state=DataState.CONFIRMED,
            source="google_places", method=EvidenceMethod.STRUCTURED_FIELD, confidence=ConfidenceLevel.HIGH,
        )
    )
    db.flush()


class TestPreconditions:
    def test_company_not_found_raises_lookup_error(self, db_session: Session) -> None:
        service = OpportunityScoringService(db_session)
        with pytest.raises(LookupError):
            service.compute(uuid.uuid4())

    def test_no_audit_snapshot_raises_value_error(self, db_session: Session) -> None:
        company = _company(db_session)
        service = OpportunityScoringService(db_session)
        with pytest.raises(ValueError):
            service.compute(company.id)


class TestComputeAndPersist:
    def test_computes_and_persists_score(self, db_session: Session) -> None:
        company = _company(db_session, category_slug="restaurante")
        _audit_snapshot(db_session, company, site_state=DataState.NOT_DETECTED)
        _evidence(db_session, company, "rating", "4.5")
        _evidence(db_session, company, "review_count", "30")
        _evidence(db_session, company, "phone", "+5511987654321")

        service = OpportunityScoringService(db_session)
        score = service.compute(company.id)

        assert score.id is not None
        assert score.score is not None
        assert score.tier is not None
        assert score.confidence is not None
        assert score.scoring_version == SCORING_VERSION
        assert score.breakdown is not None
        assert db_session.query(OpportunityScore).count() == 1

    def test_recompute_updates_same_row_not_a_new_one(self, db_session: Session) -> None:
        company = _company(db_session)
        _audit_snapshot(db_session, company, site_state=DataState.NOT_DETECTED)

        service = OpportunityScoringService(db_session)
        first = service.compute(company.id)
        first_id = first.id
        second = service.compute(company.id)

        assert second.id == first_id
        assert db_session.query(OpportunityScore).count() == 1

    def test_new_audit_snapshot_creates_a_new_score_preserving_history(self, db_session: Session) -> None:
        company = _company(db_session)
        _audit_snapshot(db_session, company, site_state=DataState.NOT_DETECTED)
        service = OpportunityScoringService(db_session)
        service.compute(company.id)

        _audit_snapshot(db_session, company, site_state=DataState.CONFIRMED, quality_score=80.0)
        service.compute(company.id)

        assert db_session.query(OpportunityScore).count() == 2

    def test_get_latest_returns_most_recent_score(self, db_session: Session) -> None:
        company = _company(db_session)
        _audit_snapshot(db_session, company, site_state=DataState.NOT_DETECTED)
        service = OpportunityScoringService(db_session)
        first = service.compute(company.id)

        _audit_snapshot(db_session, company, site_state=DataState.CONFIRMED, quality_score=50.0)
        second = service.compute(company.id)

        latest = service.get_latest(company.id)
        assert latest is not None
        assert latest.id == second.id
        assert latest.id != first.id

    def test_get_latest_returns_none_without_any_score(self, db_session: Session) -> None:
        company = _company(db_session)
        service = OpportunityScoringService(db_session)
        assert service.get_latest(company.id) is None
