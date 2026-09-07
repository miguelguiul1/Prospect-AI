"""Testes de `POST /api/prototypes/{id}/generate` e
`GET /api/prototypes/{id}/generations/{generation_id}` (Fase 9 /
Prompt 11).

Sem `ANTHROPIC_API_KEY` no ambiente de teste — todo teste aqui injeta um
`FakeGenerationProvider` no ponto de resolução de
`PrototypeGenerationService` (mesmo padrão de
`tests/outreach/test_api.py`), nunca uma chamada real."""
from __future__ import annotations

import uuid

import pytest

from app.domains.audit.enums import AuditStatus
from app.domains.audit.models import AuditSnapshot
from app.domains.companies.models import Company
from app.domains.prototypes.generation.fake_provider import FakeGenerationProvider


@pytest.fixture(autouse=True)
def _bypass_rate_limit(monkeypatch: pytest.MonkeyPatch):
    """Mesma razão de tests/outreach/test_api.py: desde F8.3/Prompt 11, a
    geração usa on_unavailable="fail_closed" — sem este bypass, todo
    teste aqui seria bloqueado com 429 antes de exercitar a lógica que de
    fato quer testar. TestRateLimiting abaixo desfaz o bypass."""
    monkeypatch.setattr("app.api.routes.prototypes.check_and_increment", lambda *a, **k: True)


@pytest.fixture
def fake_ai_provider(monkeypatch: pytest.MonkeyPatch):
    provider = FakeGenerationProvider()
    monkeypatch.setattr(
        "app.domains.prototypes.generation.service.get_generation_provider", lambda settings: provider
    )
    return provider


def _headers(client, email: str = "vendedor@example.com") -> dict:
    token = client.post(
        "/api/auth/register", json={"email": email, "name": "Vendedor", "password": "senhaforte123"}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _company_with_context(db, name: str = "Padaria Central") -> Company:
    company = Company(canonical_name=name)
    db.add(company)
    db.flush()
    db.add(AuditSnapshot(company_id=company.id, run_id=uuid.uuid4(), status=AuditStatus.COMPLETED))
    db.flush()
    db.commit()
    return company


def _prototype_with_opportunity(client, db, headers) -> tuple[str, str]:
    """Cria Company + Opportunity (acesso) + Prototype — retorna
    (prototype_id, company_id)."""
    company = _company_with_context(db)
    client.post("/api/crm/opportunities", json={"company_id": str(company.id)}, headers=headers)
    created = client.post(
        "/api/prototypes", json={"name": "Site", "company_id": str(company.id)}, headers=headers
    ).json()
    return created["id"], str(company.id)


class TestGeneratePrototype:
    def test_successful_generation_returns_succeeded_and_populates_components(
        self, client, db_session, fake_ai_provider
    ) -> None:
        headers = _headers(client)
        prototype_id, _ = _prototype_with_opportunity(client, db_session, headers)

        response = client.post(f"/api/prototypes/{prototype_id}/generate", headers=headers)

        assert response.status_code == 202
        body = response.json()
        assert body["status"] == "succeeded"
        assert body["provider"] == "fake"

        reloaded = client.get(f"/api/prototypes/{prototype_id}", headers=headers).json()
        assert len(reloaded["components"]) > 0

    def test_generation_without_token_is_unauthorized(self, client, db_session) -> None:
        headers = _headers(client)
        prototype_id, _ = _prototype_with_opportunity(client, db_session, headers)

        response = client.post(f"/api/prototypes/{prototype_id}/generate")
        assert response.status_code == 401

    def test_generation_for_a_prototype_i_dont_have_access_to_returns_404(
        self, client, db_session, fake_ai_provider
    ) -> None:
        owner_headers = _headers(client, "dono@example.com")
        prototype_id, _ = _prototype_with_opportunity(client, db_session, owner_headers)

        other_headers = _headers(client, "outro@example.com")
        response = client.post(f"/api/prototypes/{prototype_id}/generate", headers=other_headers)

        assert response.status_code == 404

    def test_generating_for_unknown_prototype_returns_404(self, client, fake_ai_provider) -> None:
        headers = _headers(client)
        response = client.post(f"/api/prototypes/{uuid.uuid4()}/generate", headers=headers)
        assert response.status_code == 404

    def test_a_second_generation_while_one_is_pending_returns_409(self, client, db_session, fake_ai_provider) -> None:
        headers = _headers(client)
        prototype_id, company_id = _prototype_with_opportunity(client, db_session, headers)

        from app.domains.prototypes.models import GenerationRun, GenerationStatus

        db_session.add(
            GenerationRun(
                prototype_id=uuid.UUID(prototype_id),
                company_id=uuid.UUID(company_id),
                status=GenerationStatus.PENDING,
                prompt_version="v1",
                context_version="v1",
            )
        )
        db_session.commit()

        response = client.post(f"/api/prototypes/{prototype_id}/generate", headers=headers)

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "generation_in_progress"

    def test_generation_for_a_company_with_no_evidence_or_audit_fails_cleanly(
        self, client, db_session, fake_ai_provider
    ) -> None:
        headers = _headers(client)
        company = Company(canonical_name="Empresa Sem Dado Nenhum")
        db_session.add(company)
        db_session.flush()
        client.post("/api/crm/opportunities", json={"company_id": str(company.id)}, headers=headers)
        created = client.post(
            "/api/prototypes", json={"name": "Site", "company_id": str(company.id)}, headers=headers
        ).json()

        response = client.post(f"/api/prototypes/{created['id']}/generate", headers=headers)

        assert response.status_code == 202  # a requisição foi aceita e processada
        body = response.json()
        assert body["status"] == "failed"
        assert body["error_code"] == "InsufficientContextError"


class TestGetGeneration:
    def test_get_existing_generation(self, client, db_session, fake_ai_provider) -> None:
        headers = _headers(client)
        prototype_id, _ = _prototype_with_opportunity(client, db_session, headers)
        created = client.post(f"/api/prototypes/{prototype_id}/generate", headers=headers).json()

        response = client.get(f"/api/prototypes/{prototype_id}/generations/{created['id']}", headers=headers)

        assert response.status_code == 200
        assert response.json()["status"] == "succeeded"

    def test_get_unknown_generation_returns_404(self, client, db_session, fake_ai_provider) -> None:
        headers = _headers(client)
        prototype_id, _ = _prototype_with_opportunity(client, db_session, headers)

        response = client.get(f"/api/prototypes/{prototype_id}/generations/{uuid.uuid4()}", headers=headers)
        assert response.status_code == 404

    def test_get_generation_of_a_prototype_i_dont_have_access_to_returns_404(
        self, client, db_session, fake_ai_provider
    ) -> None:
        owner_headers = _headers(client, "dono2@example.com")
        prototype_id, _ = _prototype_with_opportunity(client, db_session, owner_headers)
        created = client.post(f"/api/prototypes/{prototype_id}/generate", headers=owner_headers).json()

        other_headers = _headers(client, "outro2@example.com")
        response = client.get(
            f"/api/prototypes/{prototype_id}/generations/{created['id']}", headers=other_headers
        )
        assert response.status_code == 404


class TestObservability:
    """Fase 9 / Prompt 11, seção 8: métricas via app/core/metrics.py
    (Fase 8.6), nunca a API key nem o conteúdo bruto do prompt em log."""

    def test_metrics_reflect_the_generation(self, client, db_session, fake_ai_provider) -> None:
        headers = _headers(client)
        prototype_id, _ = _prototype_with_opportunity(client, db_session, headers)

        client.post(f"/api/prototypes/{prototype_id}/generate", headers=headers)

        metrics_text = client.get("/metrics").text
        assert 'ai_requests_total{domain="prototype_generation",status="completed"}' in metrics_text
        # Labels são renderizados em ordem alfabética pelo nome do label
        # (ver app.core.metrics), não na ordem em que foram passados.
        assert 'ai_tokens_total{direction="input",domain="prototype_generation"}' in metrics_text
        assert 'ai_tokens_total{direction="output",domain="prototype_generation"}' in metrics_text


class TestRateLimiting:
    """Não usa o fixture `_bypass_rate_limit` (module-level, autouse) —
    aqui queremos o comportamento real de `check_and_increment` contra o
    Redis indisponível deste ambiente de teste."""

    def test_generation_is_blocked_when_redis_is_unavailable_fail_closed(
        self, client, db_session, monkeypatch, fake_ai_provider
    ) -> None:
        monkeypatch.undo()  # desfaz só o autouse deste teste
        headers = _headers(client)
        prototype_id, _ = _prototype_with_opportunity(client, db_session, headers)

        response = client.post(f"/api/prototypes/{prototype_id}/generate", headers=headers)

        assert response.status_code == 429
        assert response.json()["error"]["code"] == "prototype_generation_rate_limited"
