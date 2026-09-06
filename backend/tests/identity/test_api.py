"""Testes de `POST /api/identity/resolve` — só leitura, nunca persiste."""
from __future__ import annotations

from app.domains.companies.models import Company


def test_resolve_returns_no_match_when_nothing_exists(client) -> None:
    response = client.post(
        "/api/identity/resolve",
        json={"source": "google_places", "external_id": "ChIJ_1", "name": "Empresa Nova"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "no_match"
    assert body["matched_company_id"] is None


def test_resolve_is_read_only(client, db_session) -> None:
    """Chamar o endpoint não deve criar nenhuma Company, mesmo quando o
    resultado seria MATCH/INCONCLUSIVE numa persistência real."""
    response = client.post(
        "/api/identity/resolve",
        json={"source": "google_places", "external_id": "ChIJ_1", "name": "Empresa Nova"},
    )

    assert response.status_code == 200
    assert db_session.query(Company).count() == 0


def test_resolve_finds_match_against_existing_company(client, db_session) -> None:
    from app.domains.evidence.enums import ConfidenceLevel, DataState, EvidenceMethod
    from app.domains.evidence.models import Evidence

    company = Company(canonical_name="Restaurante São João")
    db_session.add(company)
    db_session.flush()
    db_session.add(
        Evidence(
            company_id=company.id, field="phone", value="+5511987654321",
            state=DataState.CONFIRMED, source="google_places",
            method=EvidenceMethod.STRUCTURED_FIELD, confidence=ConfidenceLevel.HIGH,
        )
    )
    db_session.flush()

    response = client.post(
        "/api/identity/resolve",
        json={
            "source": "openstreetmap", "external_id": "node/1",
            "name": "REST. SAO JOAO", "phone": "+5511987654321",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "match"
    assert body["matched_company_id"] == str(company.id)

    # Continua sem persistir nada — endpoint é só leitura.
    assert db_session.query(Company).count() == 1


def test_resolve_validates_required_fields(client) -> None:
    response = client.post("/api/identity/resolve", json={"name": "Sem fonte nem external_id"})

    assert response.status_code == 422
