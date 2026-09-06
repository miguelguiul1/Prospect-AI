"""Testes de `GET /api/companies` e `GET /api/companies/{company_id}` —
API de leitura agregada usada pelo Dashboard (Fase 5)."""
from __future__ import annotations

import uuid

from app.domains.audit.enums import AuditStatus
from app.domains.audit.models import AuditSnapshot
from app.domains.companies.models import Company
from app.domains.evidence.enums import ConfidenceLevel, DataState


def _company(db, name: str = "Empresa Teste") -> Company:
    company = Company(canonical_name=name)
    db.add(company)
    db.flush()
    return company


def test_list_companies_empty(client) -> None:
    response = client.get("/api/companies")
    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    assert body["total"] == 0


def test_list_companies_reflects_audit_and_score(client, db_session) -> None:
    company = _company(db_session)
    db_session.commit()

    client.post(f"/api/audit/{company.id}")
    client.post(f"/api/scoring/{company.id}")

    response = client.get("/api/companies")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    item = body["items"][0]
    assert item["id"] == str(company.id)
    assert item["has_audit"] is True
    assert item["site_state"] == "not_detected"
    assert item["opportunity_score"] is not None
    assert item["opportunity_tier"] is not None


def test_list_companies_filters_by_site_state(client, db_session) -> None:
    with_site = _company(db_session, "Com site")
    without_site = _company(db_session, "Sem site")
    db_session.add(AuditSnapshot(company_id=with_site.id, run_id=uuid.uuid4(), status=AuditStatus.COMPLETED, site_state=DataState.CONFIRMED))
    db_session.add(AuditSnapshot(company_id=without_site.id, run_id=uuid.uuid4(), status=AuditStatus.COMPLETED, site_state=DataState.NOT_DETECTED))
    db_session.commit()

    response = client.get("/api/companies", params={"site_state": "not_detected"})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["canonical_name"] == "Sem site"


def test_list_companies_search_by_name(client, db_session) -> None:
    _company(db_session, "Padaria Central")
    _company(db_session, "Academia Fit")
    db_session.commit()

    response = client.get("/api/companies", params={"q": "padaria"})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["canonical_name"] == "Padaria Central"


def test_list_companies_pagination(client, db_session) -> None:
    for i in range(3):
        _company(db_session, f"Empresa {i}")
    db_session.commit()

    response = client.get("/api/companies", params={"limit": 1, "offset": 1})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert len(body["items"]) == 1
    assert body["limit"] == 1
    assert body["offset"] == 1


def test_dashboard_stats_empty(client) -> None:
    response = client.get("/api/companies/meta/stats")

    assert response.status_code == 200
    assert response.json() == {
        "total_companies": 0,
        "audited_companies": 0,
        "high_opportunity_companies": 0,
        "average_opportunity_score": None,
    }


def test_dashboard_stats_reflect_real_data(client, db_session) -> None:
    company = _company(db_session)
    db_session.commit()
    client.post(f"/api/audit/{company.id}")
    client.post(f"/api/scoring/{company.id}")

    response = client.get("/api/companies/meta/stats")

    assert response.status_code == 200
    body = response.json()
    assert body["total_companies"] == 1
    assert body["audited_companies"] == 1
    assert body["average_opportunity_score"] is not None


def test_filter_options_reflect_only_categories_and_regions_in_use(client, db_session) -> None:
    from app.domains.companies.models import Category, Region

    db_session.add(Category(slug="barbearia", name="Barbearia"))
    db_session.add(Region(name="Recife", state="PE", country="BR"))
    db_session.commit()

    response = client.get("/api/companies/meta/filters")

    assert response.status_code == 200
    body = response.json()
    assert {"slug": "barbearia", "name": "Barbearia"} in body["categories"]
    assert {"name": "Recife", "state": "PE"} in body["regions"]


def test_filter_options_empty_by_default(client) -> None:
    response = client.get("/api/companies/meta/filters")

    assert response.status_code == 200
    assert response.json() == {"categories": [], "regions": []}


def test_get_company_detail_full(client, db_session) -> None:
    company = _company(db_session)
    from app.domains.evidence.models import Evidence
    from app.domains.evidence.enums import EvidenceMethod

    db_session.add(
        Evidence(
            company_id=company.id, field="phone", value="+5511987654321", state=DataState.CONFIRMED,
            source="google_places", method=EvidenceMethod.STRUCTURED_FIELD, confidence=ConfidenceLevel.HIGH,
        )
    )
    db_session.commit()

    client.post(f"/api/audit/{company.id}")
    client.post(f"/api/scoring/{company.id}")

    response = client.get(f"/api/companies/{company.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(company.id)
    assert len(body["evidence"]) >= 1
    assert body["latest_audit"] is not None
    assert body["latest_score"] is not None
    assert body["latest_brief"] is None


def test_get_company_detail_not_found_returns_404(client) -> None:
    response = client.get(f"/api/companies/{uuid.uuid4()}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "company_not_found"


def test_get_company_detail_without_audit_has_null_sections(client, db_session) -> None:
    company = _company(db_session)
    db_session.commit()

    response = client.get(f"/api/companies/{company.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["latest_audit"] is None
    assert body["latest_score"] is None
    assert body["latest_brief"] is None
