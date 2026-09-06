"""Testes de `POST /api/audit/{company_id}` e `GET /api/audit/{company_id}`.

Como o endpoint HTTP não permite injetar um `http_client`/`resolver` fake
diretamente, estes testes exercitam o caminho "sem candidato de website"
(determinístico, sem rede) e os casos de erro (empresa inexistente) — o
caminho de fetch real já está coberto por
tests/audit/test_service.py.
"""
from __future__ import annotations

import uuid

from app.domains.companies.models import Company
from app.domains.evidence.enums import ConfidenceLevel, DataState, EvidenceMethod
from app.domains.evidence.models import Evidence


def _company(db, name: str = "Empresa Teste") -> Company:
    company = Company(canonical_name=name)
    db.add(company)
    db.flush()
    return company


def test_post_audit_for_company_without_website_returns_not_detected(client, db_session) -> None:
    company = _company(db_session)
    db_session.commit()

    response = client.post(f"/api/audit/{company.id}")

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "completed"
    assert body["site_state"] == "not_detected"
    assert body["website_quality"]["score"] is None
    assert body["execution_mode"] == "executed_sync"


def test_post_audit_for_unknown_company_returns_404(client) -> None:
    response = client.post(f"/api/audit/{uuid.uuid4()}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "company_not_found"


def test_get_audit_returns_the_most_recent_snapshot(client, db_session) -> None:
    company = _company(db_session)
    db_session.commit()

    first = client.post(f"/api/audit/{company.id}")
    second = client.post(f"/api/audit/{company.id}")
    assert first.json()["id"] != second.json()["id"]

    response = client.get(f"/api/audit/{company.id}")

    assert response.status_code == 200
    assert response.json()["id"] == second.json()["id"]


def test_get_audit_for_company_never_audited_returns_404(client, db_session) -> None:
    company = _company(db_session)
    db_session.commit()

    response = client.get(f"/api/audit/{company.id}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "audit_not_found"


def test_post_audit_with_untrusted_only_candidate_is_not_detected(client, db_session) -> None:
    company = _company(db_session)
    db_session.add(
        Evidence(
            company_id=company.id, field="website", value="https://instagram.com/empresa",
            state=DataState.CONFIRMED, source="google_places",
            method=EvidenceMethod.STRUCTURED_FIELD, confidence=ConfidenceLevel.HIGH,
        )
    )
    db_session.commit()

    response = client.post(f"/api/audit/{company.id}")

    assert response.status_code == 202
    assert response.json()["site_state"] == "not_detected"
