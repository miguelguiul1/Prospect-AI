from __future__ import annotations

from sqlalchemy.orm import Session

from app.domains.companies.models import Company
from app.domains.evidence.enums import ConfidenceLevel, DataState, EvidenceMethod
from app.domains.evidence.models import Evidence
from app.domains.audit.website_candidate import WebsiteCandidateStatus, select_website_candidate


def _company(db: Session, name: str = "Empresa Teste") -> Company:
    company = Company(canonical_name=name)
    db.add(company)
    db.flush()
    return company


def _website_evidence(db: Session, company: Company, value: str, *, source: str = "google_places") -> Evidence:
    evidence = Evidence(
        company_id=company.id, field="website", value=value, state=DataState.CONFIRMED,
        source=source, method=EvidenceMethod.STRUCTURED_FIELD, confidence=ConfidenceLevel.HIGH,
    )
    db.add(evidence)
    db.flush()
    return evidence


class TestNoCandidate:
    def test_no_website_evidence_at_all(self, db_session: Session) -> None:
        company = _company(db_session)
        candidate = select_website_candidate(db_session, company.id)
        assert candidate.status == WebsiteCandidateStatus.NONE
        assert candidate.url is None

    def test_only_social_media_url_is_not_a_candidate(self, db_session: Session) -> None:
        company = _company(db_session)
        _website_evidence(db_session, company, "https://instagram.com/empresa")

        candidate = select_website_candidate(db_session, company.id)

        assert candidate.status == WebsiteCandidateStatus.NONE
        assert candidate.note is not None


class TestSingleTrustedCandidate:
    def test_returns_normalized_trusted_website(self, db_session: Session) -> None:
        company = _company(db_session)
        _website_evidence(db_session, company, "EMPRESA.com.br/")

        candidate = select_website_candidate(db_session, company.id)

        assert candidate.status == WebsiteCandidateStatus.FOUND
        assert candidate.url == "https://empresa.com.br"
        assert candidate.hostname == "empresa.com.br"
        assert candidate.source == "google_places"


class TestAmbiguousCandidate:
    def test_two_different_trusted_hostnames_is_ambiguous(self, db_session: Session) -> None:
        company = _company(db_session)
        old = _website_evidence(db_session, company, "https://empresa-antiga.com.br", source="openstreetmap")
        new = _website_evidence(db_session, company, "https://empresa-nova.com.br", source="google_places")
        old.mark_superseded_by(new)
        db_session.flush()

        candidate = select_website_candidate(db_session, company.id)

        assert candidate.status == WebsiteCandidateStatus.AMBIGUOUS
        assert "empresa-antiga.com.br" in candidate.note
        assert "empresa-nova.com.br" in candidate.note

    def test_same_hostname_from_different_sources_is_not_ambiguous(self, db_session: Session) -> None:
        """www vs. sem www, protocolo diferente — a mesma empresa via
        fontes diferentes não deve ser tratada como desacordo."""
        company = _company(db_session)
        old = _website_evidence(db_session, company, "http://www.empresa.com.br", source="openstreetmap")
        new = _website_evidence(db_session, company, "https://empresa.com.br/", source="google_places")
        old.mark_superseded_by(new)
        db_session.flush()

        candidate = select_website_candidate(db_session, company.id)

        assert candidate.status == WebsiteCandidateStatus.FOUND
        assert candidate.hostname == "empresa.com.br"


class TestSuperseded:
    def test_only_current_non_superseded_value_is_considered_primary(self, db_session: Session) -> None:
        company = _company(db_session)
        old = _website_evidence(db_session, company, "https://antigo.com.br")
        new = _website_evidence(db_session, company, "https://novo.com.br")
        old.mark_superseded_by(new)
        db_session.flush()

        candidate = select_website_candidate(db_session, company.id)

        assert candidate.url == "https://novo.com.br"
        assert candidate.evidence_id == new.id
