"""Testes de `POST /api/sales-brief/{company_id}` e
`GET /api/sales-brief/{company_id}`.

Nenhuma `ANTHROPIC_API_KEY` está configurada no ambiente de teste (ver
`tests/conftest.py` — só define `DATABASE_URL`/`REDIS_URL`/`APP_ENV`), então
o provider real (`AnthropicProvider`) fica indisponível de forma controlada,
sem qualquer chamada de rede — isto testa o caminho de degradação graciosa
fim-a-fim, exatamente o comportamento exigido pela Fase 4 quando nenhuma
chave é configurada.
"""
from __future__ import annotations

import uuid

import pytest

from app.domains.companies.models import Company


def _company(db, name: str = "Empresa Teste") -> Company:
    company = Company(canonical_name=name)
    db.add(company)
    db.flush()
    return company


@pytest.fixture(autouse=True)
def _bypass_rate_limit(monkeypatch: pytest.MonkeyPatch):
    """Redis nunca está disponível neste ambiente de teste (ver
    tests/conftest.py) — desde a Fase 8.3, `POST /api/sales-brief/{id}` usa
    `on_unavailable="fail_closed"` (achado R11 da auditoria F8.0: era a
    única operação de IA sem nenhum limite), então TODA chamada aqui seria
    bloqueada com 429 antes de sequer chegar na lógica de negócio que estes
    testes querem exercitar. Por padrão, contorna o rate limit; o teste
    dedicado abaixo (`TestRateLimiting`) desfaz esse bypass para provar que
    o fail-closed real funciona."""
    monkeypatch.setattr("app.api.routes.sales_brief.check_and_increment", lambda *a, **k: True)


def test_post_sales_brief_for_unknown_company_returns_404(client) -> None:
    response = client.post(f"/api/sales-brief/{uuid.uuid4()}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "company_not_found"


def test_post_sales_brief_without_opportunity_score_returns_409(client, db_session) -> None:
    company = _company(db_session)
    db_session.commit()

    response = client.post(f"/api/sales-brief/{company.id}")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "opportunity_score_required"


def test_post_sales_brief_without_api_key_degrades_gracefully(client, db_session) -> None:
    company = _company(db_session)
    db_session.commit()
    client.post(f"/api/audit/{company.id}")
    client.post(f"/api/scoring/{company.id}")

    response = client.post(f"/api/sales-brief/{company.id}")

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "failed"
    assert body["content"] is None
    assert body["error_code"] == "ProviderUnavailableError"
    assert body["execution_mode"] == "executed_sync"


def test_get_sales_brief_returns_the_most_recent_one(client, db_session) -> None:
    company = _company(db_session)
    db_session.commit()
    client.post(f"/api/audit/{company.id}")
    client.post(f"/api/scoring/{company.id}")
    posted = client.post(f"/api/sales-brief/{company.id}")

    response = client.get(f"/api/sales-brief/{company.id}")

    assert response.status_code == 200
    assert response.json()["id"] == posted.json()["id"]


def test_get_sales_brief_for_company_without_any_brief_returns_404(client, db_session) -> None:
    company = _company(db_session)
    db_session.commit()

    response = client.get(f"/api/sales-brief/{company.id}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "sales_brief_not_found"


class TestRateLimiting:
    """Não usa o fixture `_bypass_rate_limit` (module-level, autouse) —
    aqui queremos justamente o comportamento real de `check_and_increment`
    contra o Redis indisponível deste ambiente de teste."""

    def test_generation_is_blocked_when_redis_is_unavailable_fail_closed(self, client, db_session, monkeypatch) -> None:
        monkeypatch.undo()  # desfaz o autouse fixture só para este teste
        company = _company(db_session)
        db_session.commit()
        client.post(f"/api/audit/{company.id}")
        client.post(f"/api/scoring/{company.id}")

        response = client.post(f"/api/sales-brief/{company.id}")

        assert response.status_code == 429
        assert response.json()["error"]["code"] == "rate_limited"
