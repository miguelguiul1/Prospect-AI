"""Testes de `/api/crm/opportunities/{id}/outreach/*` (Fase 7).

Sem `ANTHROPIC_API_KEY` configurada no ambiente de teste (mesma situação já
coberta por `tests/briefing/test_api.py`), então toda geração real degrada
graciosamente — nenhuma chamada de rede acontece. Isso deixava o caminho de
SUCESSO de `generate_outreach`, e as rotas `edit`/`transition` inteiras,
sem nenhum teste (Prompt 10, seção 3 — auditoria de cobertura: não havia
como sequer criar um Outreach via API para exercitá-las). `TestGenerateOutreachSuccess`
e as classes abaixo dela usam o mesmo padrão de provider fake já
estabelecido em `tests/outreach/test_service.py`, injetado via
monkeypatch de `app.domains.outreach.service.get_provider` (o ponto onde
`OutreachService` resolve o provider quando nenhum é passado no
construtor — a rota HTTP nunca injeta um, então este é o único ponto de
override possível para um teste de API).
"""
from __future__ import annotations

import json

import pytest

from app.domains.briefing.providers.base import ProviderResponse, SalesBriefProvider
from app.domains.companies.models import Company

_VALID_CONTENT = {
    "subject": "Uma proposta rápida para vocês",
    "message": "Olá, tudo bem? Notamos que o site de vocês pode ser modernizado...",
    "rationale": "O site não foi confirmado como ativo, então priorizamos essa dor.",
    "evidence_ids": ["site_state: not_detected"],
}


class _FakeProvider(SalesBriefProvider):
    name = "fake"

    def is_configured(self) -> bool:
        return True

    def generate(self, *, system: str, user: str, max_tokens: int | None = None) -> ProviderResponse:
        return ProviderResponse(
            content=json.dumps(_VALID_CONTENT), model="fake-model-1", duration_ms=5.0, input_tokens=80, output_tokens=40
        )


@pytest.fixture
def fake_ai_provider(monkeypatch: pytest.MonkeyPatch):
    """Injeta um provider fake no ponto de resolução de `OutreachService`
    — nunca uma chamada real à Anthropic (mesma regra de todo o projeto)."""
    monkeypatch.setattr("app.domains.outreach.service.get_provider", lambda settings: _FakeProvider())


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


class TestGenerateOutreachSuccess:
    """Caminho de sucesso — nunca exercitado antes desta fase, já que
    nenhum ambiente de teste jamais teve uma `ANTHROPIC_API_KEY` real."""

    def test_generate_returns_201_with_the_ai_generated_content(self, client, db_session, fake_ai_provider) -> None:
        headers = _headers(client)
        opp_id = _opportunity(client, db_session, headers)

        response = client.post(
            f"/api/crm/opportunities/{opp_id}/outreach/generate", json={"channel": "email"}, headers=headers
        )

        assert response.status_code == 201
        body = response.json()
        assert body["subject"] == _VALID_CONTENT["subject"]
        assert body["message"] == _VALID_CONTENT["message"]
        assert body["status"] == "draft"
        assert body["generated_by_ai"] is True

    def test_generated_outreach_is_persisted_and_listed(self, client, db_session, fake_ai_provider) -> None:
        headers = _headers(client)
        opp_id = _opportunity(client, db_session, headers)

        client.post(f"/api/crm/opportunities/{opp_id}/outreach/generate", json={"channel": "email"}, headers=headers)

        listed = client.get(f"/api/crm/opportunities/{opp_id}/outreach", headers=headers)
        assert len(listed.json()) == 1


class TestEditOutreach:
    def _create(self, client, db_session, headers) -> dict:
        opp_id = _opportunity(client, db_session, headers)
        return client.post(
            f"/api/crm/opportunities/{opp_id}/outreach/generate", json={"channel": "email"}, headers=headers
        ).json()

    def test_edit_subject_and_message_of_a_draft(self, client, db_session, fake_ai_provider) -> None:
        headers = _headers(client)
        created = self._create(client, db_session, headers)

        response = client.patch(
            f"/api/crm/outreach/{created['id']}",
            json={"subject": "Assunto editado", "message": "Mensagem editada pelo vendedor."},
            headers=headers,
        )

        assert response.status_code == 200
        body = response.json()
        assert body["subject"] == "Assunto editado"
        assert body["message"] == "Mensagem editada pelo vendedor."

    def test_editing_unknown_outreach_returns_404(self, client) -> None:
        import uuid

        headers = _headers(client)
        response = client.patch(
            f"/api/crm/outreach/{uuid.uuid4()}", json={"subject": "X"}, headers=headers
        )
        assert response.status_code == 404

    def test_editing_another_users_outreach_returns_404(self, client, db_session, fake_ai_provider) -> None:
        headers_a = _headers(client, "a2@example.com")
        headers_b = _headers(client, "b2@example.com")
        created = self._create(client, db_session, headers_a)

        response = client.patch(
            f"/api/crm/outreach/{created['id']}", json={"subject": "Invasão"}, headers=headers_b
        )
        assert response.status_code == 404

    def test_editing_a_sent_outreach_returns_409(self, client, db_session, fake_ai_provider) -> None:
        headers = _headers(client)
        created = self._create(client, db_session, headers)
        client.post(f"/api/crm/outreach/{created['id']}/transition", json={"action": "mark_sent"}, headers=headers)

        response = client.patch(
            f"/api/crm/outreach/{created['id']}", json={"subject": "Tarde demais"}, headers=headers
        )

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "outreach_not_editable"


class TestTransitionOutreach:
    def _create(self, client, db_session, headers) -> dict:
        opp_id = _opportunity(client, db_session, headers)
        return client.post(
            f"/api/crm/opportunities/{opp_id}/outreach/generate", json={"channel": "email"}, headers=headers
        ).json()

    def test_mark_ready_transitions_a_draft(self, client, db_session, fake_ai_provider) -> None:
        headers = _headers(client)
        created = self._create(client, db_session, headers)

        response = client.post(
            f"/api/crm/outreach/{created['id']}/transition", json={"action": "mark_ready"}, headers=headers
        )

        assert response.status_code == 200
        assert response.json()["status"] == "ready"

    def test_mark_sent_logs_an_activity_on_the_opportunity(self, client, db_session, fake_ai_provider) -> None:
        headers = _headers(client)
        opp_id = _opportunity(client, db_session, headers)
        created = client.post(
            f"/api/crm/opportunities/{opp_id}/outreach/generate", json={"channel": "email"}, headers=headers
        ).json()

        response = client.post(
            f"/api/crm/outreach/{created['id']}/transition", json={"action": "mark_sent"}, headers=headers
        )
        assert response.status_code == 200
        assert response.json()["status"] == "sent_manually"

        timeline = client.get(f"/api/crm/opportunities/{opp_id}/timeline", headers=headers).json()
        assert any(item["type"] == "outreach" for item in timeline)

    def test_invalid_transition_returns_409(self, client, db_session, fake_ai_provider) -> None:
        headers = _headers(client)
        created = self._create(client, db_session, headers)
        client.post(f"/api/crm/outreach/{created['id']}/transition", json={"action": "cancel"}, headers=headers)

        response = client.post(
            f"/api/crm/outreach/{created['id']}/transition", json={"action": "mark_sent"}, headers=headers
        )

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "invalid_outreach_transition"

    def test_transitioning_unknown_outreach_returns_404(self, client) -> None:
        import uuid

        headers = _headers(client)
        response = client.post(
            f"/api/crm/outreach/{uuid.uuid4()}/transition", json={"action": "cancel"}, headers=headers
        )
        assert response.status_code == 404
