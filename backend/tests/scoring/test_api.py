"""Testes de `POST /api/scoring/{company_id}` e `GET /api/scoring/{company_id}`.

Usa o endpoint de Digital Audit (`client.post("/api/audit/...")`) para
produzir um `AuditSnapshot` real primeiro — o Opportunity Score depende de
uma auditoria já ter rodado (mesma cadeia que a Fase 4 exige).
"""
from __future__ import annotations

import uuid

from app.domains.companies.models import Company


def _company(db, name: str = "Empresa Teste") -> Company:
    company = Company(canonical_name=name)
    db.add(company)
    db.flush()
    return company


def test_post_scoring_for_unknown_company_returns_404(client) -> None:
    response = client.post(f"/api/scoring/{uuid.uuid4()}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "company_not_found"


def test_post_scoring_without_any_audit_returns_409(client, db_session) -> None:
    company = _company(db_session)
    db_session.commit()

    response = client.post(f"/api/scoring/{company.id}")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "opportunity_score_precondition_failed"


def test_post_scoring_after_audit_computes_score(client, db_session) -> None:
    company = _company(db_session)
    db_session.commit()

    audit_response = client.post(f"/api/audit/{company.id}")
    assert audit_response.status_code == 202

    response = client.post(f"/api/scoring/{company.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["score"] is not None
    assert body["tier"] in ("high", "medium_high", "medium", "low", "very_low")
    assert body["confidence"] in ("high", "medium", "low")
    assert body["scoring_version"] == "v1"
    assert "dimensions" in body["breakdown"]


def test_get_scoring_returns_most_recent(client, db_session) -> None:
    company = _company(db_session)
    db_session.commit()
    client.post(f"/api/audit/{company.id}")
    posted = client.post(f"/api/scoring/{company.id}")

    response = client.get(f"/api/scoring/{company.id}")

    assert response.status_code == 200
    assert response.json()["id"] == posted.json()["id"]


def test_get_scoring_without_any_score_returns_404(client, db_session) -> None:
    company = _company(db_session)
    db_session.commit()

    response = client.get(f"/api/scoring/{company.id}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "opportunity_score_not_found"
