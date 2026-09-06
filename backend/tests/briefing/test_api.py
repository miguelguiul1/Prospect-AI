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

from app.domains.companies.models import Company


def _company(db, name: str = "Empresa Teste") -> Company:
    company = Company(canonical_name=name)
    db.add(company)
    db.flush()
    return company


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
