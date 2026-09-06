"""Testes de integração do `DigitalAuditService` contra o banco real de
teste (SQLite via `db_session`) e um `httpx.MockTransport` — nenhuma
chamada de rede real.
"""
from __future__ import annotations

import uuid

import httpx
import pytest
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.domains.audit.enums import AuditStatus
from app.domains.audit.models import AuditSnapshot, WebsiteQuality
from app.domains.audit.service import DigitalAuditService
from app.domains.companies.models import Company
from app.domains.evidence.enums import ConfidenceLevel, DataState, EvidenceMethod
from app.domains.evidence.models import Evidence


def _company(db: Session, name: str = "Barbearia Exemplo") -> Company:
    company = Company(canonical_name=name)
    db.add(company)
    db.flush()
    return company


def _website_evidence(db: Session, company: Company, value: str) -> Evidence:
    evidence = Evidence(
        company_id=company.id, field="website", value=value, state=DataState.CONFIRMED,
        source="google_places", method=EvidenceMethod.STRUCTURED_FIELD, confidence=ConfidenceLevel.HIGH,
    )
    db.add(evidence)
    db.flush()
    return evidence


def _settings() -> Settings:
    return Settings(_env_file=None, audit_http_max_retries=0)


def _fake_resolver(hostname: str) -> list[str]:
    """`*.example.com` não é um domínio real — a auditoria nunca deveria
    depender de DNS real em teste. Devolve sempre um IP público (o de
    example.com de verdade) para qualquer hostname candidato."""
    return ["93.184.216.34"]


_SAMPLE_HTML = """
<html lang="pt-BR"><head>
<title>Barbearia Exemplo - Cortes e Barba</title>
<meta name="description" content="A melhor barbearia da regiao, agende seu horario pelo site ou telefone.">
<meta name="viewport" content="width=device-width">
</head><body>
<h1>Bem-vindo</h1>
<p>Ligue (11) 98765-4321</p>
<form></form>
</body></html>
"""


def _mock_client(status_code: int = 200, *, body: bytes | None = None, content_type: str = "text/html") -> httpx.Client:
    body = body if body is not None else _SAMPLE_HTML.encode()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, headers={"content-type": content_type}, content=body)

    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)


class TestNoWebsiteCandidate:
    def test_no_website_evidence_results_in_not_detected(self, db_session: Session) -> None:
        company = _company(db_session)
        service = DigitalAuditService(db_session, settings=_settings())

        snapshot = service.start_audit(company.id)
        db_session.flush()
        service.execute(snapshot.id)

        assert snapshot.status == AuditStatus.COMPLETED
        assert snapshot.site_state == DataState.NOT_DETECTED
        assert snapshot.website_quality.score is None

    def test_only_social_media_candidate_results_in_not_detected(self, db_session: Session) -> None:
        company = _company(db_session)
        _website_evidence(db_session, company, "https://instagram.com/barbearia")
        service = DigitalAuditService(db_session, settings=_settings())

        snapshot = service.start_audit(company.id)
        db_session.flush()
        service.execute(snapshot.id)

        assert snapshot.site_state == DataState.NOT_DETECTED


class TestSuccessfulAudit:
    def test_confirmed_site_produces_score_and_evidence(self, db_session: Session) -> None:
        company = _company(db_session)
        _website_evidence(db_session, company, "https://barbearia.example.com")
        service = DigitalAuditService(db_session, settings=_settings(), http_client=_mock_client(), resolver=_fake_resolver)

        snapshot = service.start_audit(company.id)
        db_session.flush()
        service.execute(snapshot.id)

        assert snapshot.status == AuditStatus.COMPLETED
        assert snapshot.site_state == DataState.CONFIRMED
        assert snapshot.website_url == "https://barbearia.example.com"

        quality = snapshot.website_quality
        assert quality is not None
        assert quality.score is not None
        assert quality.confidence == ConfidenceLevel.HIGH
        assert set(quality.components.keys()) == {"security", "seo", "content", "ux", "technical"}

    def test_evidence_rows_are_created_with_provenance(self, db_session: Session) -> None:
        company = _company(db_session)
        _website_evidence(db_session, company, "https://barbearia.example.com")
        service = DigitalAuditService(db_session, settings=_settings(), http_client=_mock_client(), resolver=_fake_resolver)

        snapshot = service.start_audit(company.id)
        db_session.flush()
        service.execute(snapshot.id)

        evidences = {e.field: e for e in db_session.query(Evidence).filter(Evidence.audit_snapshot_id == snapshot.id).all()}

        assert evidences["website_https"].value == "true"
        assert evidences["website_status_code"].value == "200"
        assert evidences["website_title"].value == "Barbearia Exemplo - Cortes e Barba"
        assert evidences["website_contact_available"].value == "true"
        assert evidences["website_title"].confidence == ConfidenceLevel.MEDIUM
        assert evidences["website_https"].confidence == ConfidenceLevel.HIGH
        assert evidences["website_title"].source_url == "https://barbearia.example.com"
        assert evidences["website_title"].collected_at is not None

    def test_rerunning_audit_with_identical_page_does_not_duplicate_evidence(self, db_session: Session) -> None:
        company = _company(db_session)
        _website_evidence(db_session, company, "https://barbearia.example.com")

        service_1 = DigitalAuditService(db_session, settings=_settings(), http_client=_mock_client(), resolver=_fake_resolver)
        snap_1 = service_1.start_audit(company.id)
        db_session.flush()
        service_1.execute(snap_1.id)

        service_2 = DigitalAuditService(db_session, settings=_settings(), http_client=_mock_client(), resolver=_fake_resolver)
        snap_2 = service_2.start_audit(company.id)
        db_session.flush()
        service_2.execute(snap_2.id)

        # Duas execuções, dois AuditSnapshot distintos (histórico preservado)...
        assert db_session.query(AuditSnapshot).filter(AuditSnapshot.company_id == company.id).count() == 2
        # ...mas como o título não mudou, não há uma segunda Evidence de título.
        title_evidences = db_session.query(Evidence).filter(Evidence.company_id == company.id, Evidence.field == "website_title").all()
        assert len(title_evidences) == 1

    def test_changed_content_supersedes_old_evidence(self, db_session: Session) -> None:
        company = _company(db_session)
        _website_evidence(db_session, company, "https://barbearia.example.com")

        service_1 = DigitalAuditService(db_session, settings=_settings(), http_client=_mock_client(), resolver=_fake_resolver)
        snap_1 = service_1.start_audit(company.id)
        db_session.flush()
        service_1.execute(snap_1.id)

        new_html = _SAMPLE_HTML.replace("Barbearia Exemplo - Cortes e Barba", "Novo Titulo da Pagina")
        service_2 = DigitalAuditService(db_session, settings=_settings(), http_client=_mock_client(body=new_html.encode()), resolver=_fake_resolver)
        snap_2 = service_2.start_audit(company.id)
        db_session.flush()
        service_2.execute(snap_2.id)

        title_evidences = (
            db_session.query(Evidence)
            .filter(Evidence.company_id == company.id, Evidence.field == "website_title")
            .order_by(Evidence.collected_at)
            .all()
        )
        assert len(title_evidences) == 2
        old, new = title_evidences
        assert old.superseded_by_id == new.id
        assert new.value == "Novo Titulo da Pagina"


class TestNonHtmlResponse:
    def test_non_html_content_is_confirmed_but_has_no_html_evidence(self, db_session: Session) -> None:
        company = _company(db_session)
        _website_evidence(db_session, company, "https://barbearia.example.com")
        service = DigitalAuditService(
            db_session, settings=_settings(),
            http_client=_mock_client(body=b"%PDF-1.4", content_type="application/pdf"),
            resolver=_fake_resolver,
        )

        snapshot = service.start_audit(company.id)
        db_session.flush()
        service.execute(snapshot.id)

        assert snapshot.site_state == DataState.CONFIRMED
        assert snapshot.website_quality.confidence == ConfidenceLevel.LOW
        assert db_session.query(Evidence).filter(Evidence.field == "website_title").count() == 0


class TestSsrfBlocked:
    def test_url_resolving_to_private_ip_is_not_checked(self, db_session: Session) -> None:
        company = _company(db_session)
        _website_evidence(db_session, company, "http://internal.example.com")

        def resolves_to_private_network(hostname: str) -> list[str]:
            return ["10.0.0.5"]

        service = DigitalAuditService(db_session, settings=_settings(), resolver=resolves_to_private_network)
        snapshot = service.start_audit(company.id)
        db_session.flush()
        service.execute(snapshot.id)

        assert snapshot.status == AuditStatus.COMPLETED  # decisão de segurança, não uma falha
        assert snapshot.site_state == DataState.NOT_CHECKED
        assert "SSRF" in (snapshot.error_message or "")
        assert snapshot.website_quality.score is None


class TestInaccessible:
    def test_connection_failure_marks_inaccessible(self, db_session: Session) -> None:
        company = _company(db_session)
        _website_evidence(db_session, company, "https://barbearia.example.com")

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("recusado", request=request)

        client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
        service = DigitalAuditService(db_session, settings=_settings(), http_client=client, resolver=_fake_resolver)

        snapshot = service.start_audit(company.id)
        db_session.flush()
        service.execute(snapshot.id)

        assert snapshot.status == AuditStatus.COMPLETED
        assert snapshot.site_state == DataState.INACCESSIBLE
        assert snapshot.website_quality.score is None


class TestAmbiguousCandidate:
    def test_conflicting_sources_result_in_inconclusive(self, db_session: Session) -> None:
        company = _company(db_session)
        old = _website_evidence(db_session, company, "https://antigo.com.br")
        new = _website_evidence(db_session, company, "https://novo.com.br")
        old.mark_superseded_by(new)
        db_session.flush()

        service = DigitalAuditService(db_session, settings=_settings())
        snapshot = service.start_audit(company.id)
        db_session.flush()
        service.execute(snapshot.id)

        assert snapshot.status == AuditStatus.COMPLETED
        assert snapshot.site_state == DataState.INCONCLUSIVE
        assert snapshot.website_quality.score is None


class TestUnexpectedFailure:
    def test_company_not_found_raises_value_error_on_start(self, db_session: Session) -> None:
        service = DigitalAuditService(db_session, settings=_settings())
        with pytest.raises(ValueError):
            service.start_audit(uuid.uuid4())

    def test_unknown_snapshot_raises_value_error_on_execute(self, db_session: Session) -> None:
        service = DigitalAuditService(db_session, settings=_settings())
        with pytest.raises(ValueError):
            service.execute(uuid.uuid4())
