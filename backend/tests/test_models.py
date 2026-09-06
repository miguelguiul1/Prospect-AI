"""Testes de fundação do modelo de dados (Fase 0).

Cobrem exatamente os critérios de conclusão da Fase 0 relacionados a banco:
Company sem depender de place_id, CompanySource com múltiplas fontes,
Evidence com proveniência e histórico append-only, AuditSnapshot histórico,
e os placeholders de WebsiteQuality/OpportunityScore/SearchRun/
IdentityMergeLog.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domains.audit.models import AuditSnapshot, WebsiteQuality
from app.domains.companies.models import Company
from app.domains.discovery.models import SearchRun, SearchRunStatus
from app.domains.evidence.enums import ConfidenceLevel, DataState, EvidenceMethod
from app.domains.evidence.models import Evidence
from app.domains.identity.enums import MatchDecision
from app.domains.identity.models import CompanySource, DedupCandidate, DedupCandidateStatus, IdentityMergeLog
from app.domains.scoring.models import OpportunityScore, OpportunityTier


def _make_company(db_session: Session, name: str = "Barbearia Modelo") -> Company:
    company = Company(canonical_name=name)
    db_session.add(company)
    db_session.flush()
    return company


class TestCompanyIdentity:
    def test_company_has_no_external_identifier_column(self) -> None:
        """Trava arquitetural: Company não pode voltar a depender de um
        place_id (ou qualquer identificador de fonte externa) — arquitetura
        v0.2, seção 07."""
        columns = set(Company.__table__.columns.keys())

        assert "place_id" not in columns
        assert not any("external_id" in column for column in columns)
        assert not any("place_id" in column for column in columns)

    def test_company_can_be_created_with_only_internal_fields(self, db_session: Session) -> None:
        company = _make_company(db_session)

        assert company.id is not None
        assert company.status.value == "active"
        assert company.created_at is not None


class TestCompanySource:
    def test_company_can_have_multiple_sources(self, db_session: Session) -> None:
        company = _make_company(db_session)

        google_source = CompanySource(
            company_id=company.id,
            source="google_places",
            external_id="ChIJ_fake_place_id",
            confidence=ConfidenceLevel.HIGH,
        )
        osm_source = CompanySource(
            company_id=company.id,
            source="openstreetmap",
            external_id="node/123456",
            confidence=ConfidenceLevel.MEDIUM,
        )
        db_session.add_all([google_source, osm_source])
        db_session.flush()
        db_session.refresh(company)

        assert len(company.sources) == 2
        assert {source.source for source in company.sources} == {"google_places", "openstreetmap"}

    def test_duplicate_source_and_external_id_is_rejected(self, db_session: Session) -> None:
        """(source, external_id) é único — é o que torna reprocessar a
        mesma fonte idempotente por construção (arquitetura v0.2, seção 07)."""
        company = _make_company(db_session)
        db_session.add(
            CompanySource(
                company_id=company.id,
                source="google_places",
                external_id="ChIJ_duplicado",
                confidence=ConfidenceLevel.HIGH,
            )
        )
        db_session.flush()

        db_session.add(
            CompanySource(
                company_id=company.id,
                source="google_places",
                external_id="ChIJ_duplicado",
                confidence=ConfidenceLevel.HIGH,
            )
        )
        with pytest.raises(IntegrityError):
            db_session.flush()

    def test_source_can_record_reported_coordinates(self, db_session: Session) -> None:
        """Coordenadas (Fase 2) pertencem à fonte, não à Company — cada
        fonte pode reportar uma localização própria (arquitetura Fase 2,
        seção 7)."""
        company = _make_company(db_session)
        source = CompanySource(
            company_id=company.id,
            source="google_places",
            external_id="ChIJ_geo",
            confidence=ConfidenceLevel.HIGH,
            latitude=-23.5505,
            longitude=-46.6333,
        )
        db_session.add(source)
        db_session.flush()

        assert source.latitude == -23.5505
        assert source.longitude == -46.6333


class TestDedupCandidate:
    def test_records_a_match_decision_as_auto_resolved(self, db_session: Session) -> None:
        existing = _make_company(db_session, "Restaurante São João")

        row = DedupCandidate(
            company_id=existing.id,
            resulting_company_id=existing.id,
            source="openstreetmap",
            external_id="node/1",
            decision=MatchDecision.MATCH,
            confidence=ConfidenceLevel.HIGH,
            reasons=["telefone igual", "nome compatível"],
            signals={"phone_match": True},
            status=DedupCandidateStatus.AUTO_RESOLVED,
        )
        db_session.add(row)
        db_session.flush()

        assert row.reviewed_at is None
        assert row.reasons == ["telefone igual", "nome compatível"]

    def test_inconclusive_defaults_to_pending_review(self, db_session: Session) -> None:
        existing = _make_company(db_session, "Restaurante do João")
        new_company = _make_company(db_session, "Padaria Estrela")

        row = DedupCandidate(
            company_id=existing.id,
            resulting_company_id=new_company.id,
            source="google_places",
            external_id="ChIJ_x",
            decision=MatchDecision.INCONCLUSIVE,
            confidence=ConfidenceLevel.MEDIUM,
            reasons=["telefone igual, mas nome não corrobora"],
            signals={"phone_match": True},
            status=DedupCandidateStatus.PENDING_REVIEW,
        )
        db_session.add(row)
        db_session.flush()

        assert row.status == DedupCandidateStatus.PENDING_REVIEW
        assert row.resulting_company_id != row.company_id


class TestEvidenceAppendOnly:
    def test_evidence_requires_provenance_fields(self, db_session: Session) -> None:
        company = _make_company(db_session)

        evidence = Evidence(
            company_id=company.id,
            field="website",
            value="https://empresa.com.br",
            state=DataState.CONFIRMED,
            source="google_places",
            method=EvidenceMethod.STRUCTURED_FIELD,
            confidence=ConfidenceLevel.HIGH,
        )
        db_session.add(evidence)
        db_session.flush()

        assert evidence.collected_at is not None
        assert evidence.source == "google_places"
        assert evidence.method == EvidenceMethod.STRUCTURED_FIELD

    def test_superseding_evidence_never_deletes_the_old_row(self, db_session: Session) -> None:
        """Reprocessar uma empresa não pode apagar o que já se sabia — a
        evidência antiga permanece, apenas apontando para a nova."""
        company = _make_company(db_session)

        old_evidence = Evidence(
            company_id=company.id,
            field="website",
            value=None,
            state=DataState.NOT_DETECTED,
            source="custom_search",
            method=EvidenceMethod.HEURISTIC_MATCH,
            confidence=ConfidenceLevel.MEDIUM,
        )
        db_session.add(old_evidence)
        db_session.flush()
        old_evidence_id = old_evidence.id

        new_evidence = Evidence(
            company_id=company.id,
            field="website",
            value="https://empresa.com.br",
            state=DataState.CONFIRMED,
            source="google_places",
            method=EvidenceMethod.STRUCTURED_FIELD,
            confidence=ConfidenceLevel.HIGH,
        )
        db_session.add(new_evidence)
        db_session.flush()

        old_evidence.mark_superseded_by(new_evidence)
        db_session.flush()

        db_session.expire_all()
        preserved = db_session.get(Evidence, old_evidence_id)
        assert preserved is not None
        assert preserved.state == DataState.NOT_DETECTED  # valor antigo intacto
        assert preserved.superseded_by_id == new_evidence.id

    def test_data_state_is_never_binary(self) -> None:
        """As seis fases de checagem exigidas pela arquitetura v0.2 (seção
        05) precisam existir como estados distintos, não como um booleano."""
        assert {state.value for state in DataState} == {
            "confirmed",
            "not_detected",
            "inconclusive",
            "inaccessible",
            "not_checked",
            "stale",
        }


class TestAuditSnapshotHistory:
    def test_company_accumulates_multiple_audit_snapshots(self, db_session: Session) -> None:
        company = _make_company(db_session)

        first_run = AuditSnapshot(company_id=company.id, run_id=uuid.uuid4())
        second_run = AuditSnapshot(company_id=company.id, run_id=uuid.uuid4())
        db_session.add_all([first_run, second_run])
        db_session.flush()
        db_session.refresh(company)

        assert len(company.audit_snapshots) == 2
        assert first_run.run_id != second_run.run_id
        assert first_run.presence_level is None  # calculado só na Fase 3

    def test_evidence_can_be_grouped_by_audit_run(self, db_session: Session) -> None:
        company = _make_company(db_session)
        snapshot = AuditSnapshot(company_id=company.id, run_id=uuid.uuid4())
        db_session.add(snapshot)
        db_session.flush()

        evidence = Evidence(
            company_id=company.id,
            audit_snapshot_id=snapshot.id,
            field="instagram",
            value="https://instagram.com/empresa",
            state=DataState.CONFIRMED,
            source="manual",
            method=EvidenceMethod.MANUAL,
            confidence=ConfidenceLevel.HIGH,
        )
        db_session.add(evidence)
        db_session.flush()
        db_session.refresh(snapshot)

        assert len(snapshot.evidences) == 1
        assert snapshot.evidences[0].field == "instagram"

    def test_website_quality_and_opportunity_score_are_one_to_one_with_snapshot(
        self, db_session: Session
    ) -> None:
        company = _make_company(db_session)
        snapshot = AuditSnapshot(company_id=company.id, run_id=uuid.uuid4())
        db_session.add(snapshot)
        db_session.flush()

        quality = WebsiteQuality(audit_snapshot_id=snapshot.id)
        score = OpportunityScore(audit_snapshot_id=snapshot.id, tier=OpportunityTier.HIGH)
        db_session.add_all([quality, score])
        db_session.flush()
        db_session.refresh(snapshot)

        assert snapshot.website_quality.id == quality.id
        assert snapshot.opportunity_score.tier == OpportunityTier.HIGH
        # placeholders da Fase 0: nenhum sinal/score real ainda
        assert quality.signals is None
        assert score.score is None


class TestIdentityMergeLog:
    def test_merge_log_records_which_signals_justified_the_merge(self, db_session: Session) -> None:
        primary = _make_company(db_session, "Barbearia do Zé - Matriz")
        duplicate = _make_company(db_session, "Barbearia do Zé")

        merge_log = IdentityMergeLog(
            primary_company_id=primary.id,
            merged_company_id=duplicate.id,
            reason="Mesmo telefone e proximidade geográfica",
            signals={"phone_match": True, "geo_distance_m": 12},
            decided_by="system_auto",
        )
        db_session.add(merge_log)
        db_session.flush()

        assert merge_log.reverted_at is None
        assert merge_log.signals["phone_match"] is True


class TestSearchRun:
    def test_search_run_starts_pending(self, db_session: Session) -> None:
        run = SearchRun(
            region_query="Curitiba, PR",
            segment_query="barbearias",
            provider="google_places",
            parameters={},
        )
        db_session.add(run)
        db_session.flush()

        assert run.status == SearchRunStatus.PENDING
        assert run.cost_estimate is None
