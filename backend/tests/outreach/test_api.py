"""Testes de `/api/crm/opportunities/{id}/outreach/*` (Fase 7).

Sem `ANTHROPIC_API_KEY` configurada no ambiente de teste (mesma situação já
coberta por `tests/briefing/test_api.py`), então toda geração real degrada
graciosamente — nenhuma chamada de rede acontece.
"""
from __future__ import annotations

import pytest

from app.domains.companies.models import Company


@pytest.fixture(autouse=True)
def _bypass_rate_limit(monkeypatch: pytest.MonkeyPatch):
    """Mesma razão de `tests/briefing/test_api.py`: desde a Fase 8.3, a
    geração de Outreach usa `on_unavailable="fail_closed"` — sem este
    bypass, todo teste aqui seria bloqueado com 429 antes de exercitar a
    lógica que de fato quer testar. `TestRateLimiting` abaixo desfaz o
    bypass para provar o fail-closed real."""
    monkeypatch.setattr("app.api.routes.outreach.check_and_increment", lambda *a, **k: True)


def _headers(client, email: str = "vendedor@example.com") -> dict:
    token = client.post(
        "/api/auth/register", json={"email": email, "name": "Vendedor", "password": "senhaforte123"}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _company(db, name: str = "Empresa Teste") -> Company:
    company = Company(canonical_name=name)
    db.add(company)
    db.flush()
    db.commit()
    return company


def _opportunity(client, db, headers) -> str:
    company = _company(db)
    return client.post("/api/crm/opportunities", json={"company_id": str(company.id)}, headers=headers).json()["id"]


class TestGenerateOutreach:
    def test_without_api_key_degrades_gracefully(self, client, db_session) -> None:
        headers = _headers(client)
        opp_id = _opportunity(client, db_session, headers)

        response = client.post(
            f"/api/crm/opportunities/{opp_id}/outreach/generate", json={"channel": "email"}, headers=headers
        )

        assert response.status_code == 502
        assert response.json()["error"]["code"] == "outreach_generation_failed"

    def test_no_outreach_row_is_persisted_on_failure(self, client, db_session) -> None:
        headers = _headers(client)
        opp_id = _opportunity(client, db_session, headers)

        client.post(f"/api/crm/opportunities/{opp_id}/outreach/generate", json={"channel": "email"}, headers=headers)

        listed = client.get(f"/api/crm/opportunities/{opp_id}/outreach", headers=headers)
        assert listed.json() == []

    def test_invalid_contact_for_a_different_company_is_rejected(self, client, db_session) -> None:
        headers = _headers(client)
        opp_id = _opportunity(client, db_session, headers)
        other_company = _company(db_session, name="Outra Empresa")

        response = client.post(
            f"/api/crm/opportunities/{opp_id}/outreach/generate",
            json={"channel": "email", "contact_id": str(other_company.id)},
            headers=headers,
        )
        assert response.status_code == 422

    def test_generate_on_another_users_opportunity_is_not_found(self, client, db_session) -> None:
        headers_a = _headers(client, "a@example.com")
        headers_b = _headers(client, "b@example.com")
        opp_id = _opportunity(client, db_session, headers_a)

        response = client.post(
            f"/api/crm/opportunities/{opp_id}/outreach/generate", json={"channel": "email"}, headers=headers_b
        )
        assert response.status_code == 404


class TestOutreachIDORAndTransitions:
    def test_listing_another_users_outreach_history_is_not_found(self, client, db_session) -> None:
        headers_a = _headers(client, "a@example.com")
        headers_b = _headers(client, "b@example.com")
        opp_id = _opportunity(client, db_session, headers_a)

        response = client.get(f"/api/crm/opportunities/{opp_id}/outreach", headers=headers_b)
        assert response.status_code == 404


class TestRateLimiting:
    """Não usa o fixture `_bypass_rate_limit` (module-level, autouse) —
    aqui queremos o comportamento real de `check_and_increment` contra o
    Redis indisponível deste ambiente de teste (Fase 8.3)."""

    def test_generation_is_blocked_when_redis_is_unavailable_fail_closed(self, client, db_session, monkeypatch) -> None:
        monkeypatch.undo()  # desfaz o autouse fixture só para este teste
        headers = _headers(client)
        opp_id = _opportunity(client, db_session, headers)

        response = client.post(
            f"/api/crm/opportunities/{opp_id}/outreach/generate", json={"channel": "email"}, headers=headers
        )

        assert response.status_code == 429
        assert response.json()["error"]["code"] == "outreach_rate_limited"
