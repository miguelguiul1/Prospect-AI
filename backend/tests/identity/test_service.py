"""Testes de integração do `IdentityResolutionService` contra o banco real
de teste (SQLite via `db_session`, ver conftest.py) — sem mocks de banco.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy.orm import Session

from app.domains.companies.models import Company, CompanyStatus, Region
from app.domains.discovery.dto import DiscoveredCompany
from app.domains.evidence.enums import ConfidenceLevel, DataState, EvidenceMethod
from app.domains.evidence.models import Evidence
from app.domains.identity.enums import MatchDecision
from app.domains.identity.models import CompanySource, DedupCandidate, DedupCandidateStatus, IdentityMergeLog
from app.domains.identity.service import IdentityResolutionService


def _company(db: Session, name: str, *, region: Region | None = None) -> Company:
    company = Company(canonical_name=name, region_id=region.id if region else None)
    db.add(company)
    db.flush()
    return company


def _evidence(db: Session, company: Company, field: str, value: str, *, source: str = "google_places") -> Evidence:
    evidence = Evidence(
        company_id=company.id, field=field, value=value, state=DataState.CONFIRMED,
        source=source, method=EvidenceMethod.STRUCTURED_FIELD, confidence=ConfidenceLevel.HIGH,
    )
    db.add(evidence)
    db.flush()
    return evidence


def _source(db: Session, company: Company, source: str, external_id: str, **kwargs: object) -> CompanySource:
    row = CompanySource(
        company_id=company.id, source=source, external_id=external_id,
        confidence=ConfidenceLevel.HIGH, **kwargs,
    )
    db.add(row)
    db.flush()
    return row


class TestFindCandidates:
    def test_finds_company_by_current_phone(self, db_session: Session) -> None:
        company = _company(db_session, "Barbearia do Zé")
        _evidence(db_session, company, "phone", "+5511987654321")

        service = IdentityResolutionService(db_session)
        from app.domains.identity.profile import CompanyProfile

        candidates = service.find_candidates(
            CompanyProfile(label="x", name=None, phone="+5511987654321", address=None, website=None,
                            category=None, region_id=None, latitude=None, longitude=None)
        )

        assert [c.id for c in candidates] == [company.id]

    def test_finds_company_by_current_official_website(self, db_session: Session) -> None:
        company = _company(db_session, "Barbearia do Zé")
        _evidence(db_session, company, "website", "https://barbearia.example.com")

        service = IdentityResolutionService(db_session)
        from app.domains.identity.profile import CompanyProfile

        candidates = service.find_candidates(
            CompanyProfile(label="x", name=None, phone=None, address=None,
                            website="https://barbearia.example.com", category=None,
                            region_id=None, latitude=None, longitude=None)
        )

        assert [c.id for c in candidates] == [company.id]

    def test_does_not_block_on_untrusted_website(self, db_session: Session) -> None:
        company = _company(db_session, "Barbearia do Zé")
        _evidence(db_session, company, "website", "https://instagram.com/barbearia")

        service = IdentityResolutionService(db_session)
        from app.domains.identity.profile import CompanyProfile

        candidates = service.find_candidates(
            CompanyProfile(label="x", name=None, phone=None, address=None,
                            website="https://instagram.com/barbearia", category=None,
                            region_id=None, latitude=None, longitude=None)
        )

        assert candidates == []

    def test_finds_company_by_region(self, db_session: Session) -> None:
        region = Region(name="Interlagos", country="BR")
        db_session.add(region)
        db_session.flush()
        company = _company(db_session, "Restaurante da Esquina", region=region)

        service = IdentityResolutionService(db_session)
        from app.domains.identity.profile import CompanyProfile

        candidates = service.find_candidates(
            CompanyProfile(label="x", name=None, phone=None, address=None, website=None,
                            category=None, region_id=region.id, latitude=None, longitude=None)
        )

        assert [c.id for c in candidates] == [company.id]

    def test_no_signals_means_no_candidates(self, db_session: Session) -> None:
        _company(db_session, "Empresa Qualquer")
        service = IdentityResolutionService(db_session)
        from app.domains.identity.profile import CompanyProfile

        candidates = service.find_candidates(
            CompanyProfile(label="x", name=None, phone=None, address=None, website=None,
                            category=None, region_id=None, latitude=None, longitude=None)
        )

        assert candidates == []


class TestResolveForDiscovery:
    def test_no_candidates_returns_no_match_without_representative(self, db_session: Session) -> None:
        service = IdentityResolutionService(db_session)
        discovered = DiscoveredCompany(source="google_places", external_id="X1", name="Empresa Nova")

        resolution = service.resolve_for_discovery(discovered, region_id=None)

        assert resolution.decision == MatchDecision.NO_MATCH
        assert resolution.matched_company is None
        assert resolution.representative_company is None

    def test_single_match_sets_matched_company(self, db_session: Session) -> None:
        existing = _company(db_session, "Restaurante São João")
        _evidence(db_session, existing, "phone", "+5511987654321")

        service = IdentityResolutionService(db_session)
        discovered = DiscoveredCompany(
            source="osm", external_id="node/1", name="REST. SAO JOAO", phone="+5511987654321",
        )

        resolution = service.resolve_for_discovery(discovered, region_id=None)

        assert resolution.decision == MatchDecision.MATCH
        assert resolution.matched_company.id == existing.id

    def test_ambiguous_multiple_matches_is_inconclusive(self, db_session: Session) -> None:
        company_a = _company(db_session, "Restaurante São João - Filial A")
        _evidence(db_session, company_a, "phone", "+5511987654321")
        company_b = _company(db_session, "Restaurante São João - Filial B")
        _evidence(db_session, company_b, "phone", "+5511987654321")

        service = IdentityResolutionService(db_session)
        discovered = DiscoveredCompany(
            source="osm", external_id="node/2", name="Restaurante São João", phone="+5511987654321",
        )

        resolution = service.resolve_for_discovery(discovered, region_id=None)

        assert resolution.decision == MatchDecision.INCONCLUSIVE
        assert resolution.matched_company is None
        assert resolution.representative_company is not None


class TestRecordResolution:
    def test_match_is_recorded_as_auto_resolved(self, db_session: Session) -> None:
        existing = _company(db_session, "Restaurante São João")
        _evidence(db_session, existing, "phone", "+5511987654321")

        service = IdentityResolutionService(db_session)
        discovered = DiscoveredCompany(
            source="osm", external_id="node/1", name="REST. SAO JOAO", phone="+5511987654321",
        )
        resolution = service.resolve_for_discovery(discovered, region_id=None)
        row = service.record_resolution(discovered, resolution, resulting_company=existing)

        assert row is not None
        assert row.decision == MatchDecision.MATCH
        assert row.status == DedupCandidateStatus.AUTO_RESOLVED
        assert row.company_id == existing.id
        assert row.resulting_company_id == existing.id

    def test_inconclusive_is_recorded_as_pending_review(self, db_session: Session) -> None:
        existing = _company(db_session, "Restaurante do João")
        _evidence(db_session, existing, "phone", "+5511987654321")

        service = IdentityResolutionService(db_session)
        discovered = DiscoveredCompany(
            source="osm", external_id="node/9", name="Padaria Estrela", phone="+5511987654321",
        )
        resolution = service.resolve_for_discovery(discovered, region_id=None)
        assert resolution.decision == MatchDecision.INCONCLUSIVE

        new_company = _company(db_session, "Padaria Estrela")
        row = service.record_resolution(discovered, resolution, resulting_company=new_company)

        assert row.status == DedupCandidateStatus.PENDING_REVIEW
        assert row.resulting_company_id == new_company.id
        assert row.company_id == existing.id

    def test_no_candidates_records_nothing(self, db_session: Session) -> None:
        service = IdentityResolutionService(db_session)
        discovered = DiscoveredCompany(source="osm", external_id="node/1", name="Empresa Nova")
        resolution = service.resolve_for_discovery(discovered, region_id=None)
        new_company = _company(db_session, "Empresa Nova")

        row = service.record_resolution(discovered, resolution, resulting_company=new_company)

        assert row is None
        assert db_session.query(DedupCandidate).count() == 0


class TestMergeCompanies:
    def test_merge_reassigns_sources_and_evidence_without_data_loss(self, db_session: Session) -> None:
        """Trava de segurança contra a armadilha do cascade delete-orphan:
        reassociar CompanySource/Evidence pelo atributo de relationship não
        pode apagar nenhuma linha (seção 13 do prompt: 'impedir perda
        silenciosa de dados')."""
        primary = _company(db_session, "Barbearia do Zé - Matriz")
        _source(db_session, primary, "google_places", "ChIJ_matriz")
        _evidence(db_session, primary, "phone", "+5511987654321")

        duplicate = _company(db_session, "Barbearia do Zé")
        dup_source = _source(db_session, duplicate, "openstreetmap", "node/123")
        dup_evidence = _evidence(db_session, duplicate, "website", "https://barbearia.example.com")

        dup_source_id, dup_evidence_id, duplicate_id = dup_source.id, dup_evidence.id, duplicate.id

        service = IdentityResolutionService(db_session)
        result = service.merge_companies(
            company_a_id=primary.id, company_b_id=duplicate.id, reason="mesmo telefone e endereço",
        )

        assert result.id == primary.id

        # Nenhuma linha foi apagada — só reassociada.
        db_session.expire_all()
        moved_source = db_session.get(CompanySource, dup_source_id)
        moved_evidence = db_session.get(Evidence, dup_evidence_id)
        assert moved_source is not None
        assert moved_source.company_id == primary.id
        assert moved_evidence is not None
        assert moved_evidence.company_id == primary.id

        assert db_session.query(CompanySource).filter(CompanySource.company_id == primary.id).count() == 2
        assert db_session.query(Evidence).filter(Evidence.company_id == primary.id).count() == 2

        archived = db_session.get(Company, duplicate_id)
        assert archived.status == CompanyStatus.ARCHIVED
        # A Company descartada continua existindo — nunca é deletada.
        assert archived is not None

    def test_merge_creates_identity_merge_log(self, db_session: Session) -> None:
        primary = _company(db_session, "Barbearia do Zé - Matriz")
        duplicate = _company(db_session, "Barbearia do Zé")

        service = IdentityResolutionService(db_session)
        service.merge_companies(
            company_a_id=primary.id, company_b_id=duplicate.id,
            reason="teste", decided_by="operator:test",
        )

        log = db_session.query(IdentityMergeLog).one()
        assert log.primary_company_id == primary.id
        assert log.merged_company_id == duplicate.id
        assert log.decided_by == "operator:test"
        assert log.reverted_at is None

    def test_canonical_choice_prefers_more_sources(self, db_session: Session) -> None:
        richer = _company(db_session, "Empresa Rica em Fontes")
        _source(db_session, richer, "google_places", "g1")
        _source(db_session, richer, "openstreetmap", "o1")

        poorer = _company(db_session, "Empresa com Menos Fontes")
        _source(db_session, poorer, "google_places", "g2")

        service = IdentityResolutionService(db_session)
        primary, duplicate = service.choose_canonical(poorer, richer)

        assert primary.id == richer.id
        assert duplicate.id == poorer.id

    def test_canonical_choice_falls_back_to_older_created_at(self, db_session: Session) -> None:
        older = _company(db_session, "Empresa Antiga")
        newer = _company(db_session, "Empresa Nova")

        service = IdentityResolutionService(db_session)
        primary, duplicate = service.choose_canonical(newer, older)

        assert primary.id == older.id

    def test_cannot_merge_company_with_itself(self, db_session: Session) -> None:
        company = _company(db_session, "Empresa X")
        service = IdentityResolutionService(db_session)

        with pytest.raises(ValueError):
            service.merge_companies(company_a_id=company.id, company_b_id=company.id, reason="x")

    def test_cannot_merge_nonexistent_company(self, db_session: Session) -> None:
        company = _company(db_session, "Empresa X")
        service = IdentityResolutionService(db_session)

        with pytest.raises(ValueError):
            service.merge_companies(company_a_id=company.id, company_b_id=uuid.uuid4(), reason="x")
