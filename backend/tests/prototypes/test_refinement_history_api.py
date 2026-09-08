"""Testes de `GET /api/prototypes/{id}/refinements` (Fase 9 / Prompt 13,
seção 2 — histórico do "chat" de refinamento). Mesmo padrão de
`test_refinement_api.py`: sem `ANTHROPIC_API_KEY` no ambiente de teste,
sempre `FakeGenerationProvider` injetado."""
from __future__ import annotations

import uuid

import pytest

from app.domains.audit.enums import AuditStatus
from app.domains.audit.models import AuditSnapshot
from app.domains.companies.models import Company
from app.domains.prototypes.generation.fake_provider import FakeGenerationProvider


@pytest.fixture(autouse=True)
def _bypass_rate_limit(monkeypatch: pytest.MonkeyPatch):
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


def _generated_prototype(client, db, headers) -> str:
    company = _company_with_context(db)
    client.post("/api/crm/opportunities", json={"company_id": str(company.id)}, headers=headers)
    created = client.post(
        "/api/prototypes", json={"name": "Site", "company_id": str(company.id)}, headers=headers
    ).json()
    prototype_id = created["id"]
    generated = client.post(f"/api/prototypes/{prototype_id}/generate", headers=headers).json()
    assert generated["status"] == "succeeded"
    return prototype_id


class TestListRefinements:
    def test_empty_history_for_a_freshly_generated_prototype(self, client, db_session, fake_ai_provider) -> None:
        headers = _headers(client)
        prototype_id = _generated_prototype(client, db_session, headers)

        response = client.get(f"/api/prototypes/{prototype_id}/refinements", headers=headers)

        assert response.status_code == 200
        assert response.json() == []

    def test_initial_generation_never_appears_in_refinement_history(
        self, client, db_session, fake_ai_provider
    ) -> None:
        """A geração inicial tem `instruction=None` — ela já é a v1 na
        lista de versões, nunca uma "mensagem" do chat de refinamento."""
        headers = _headers(client)
        prototype_id = _generated_prototype(client, db_session, headers)

        history = client.get(f"/api/prototypes/{prototype_id}/refinements", headers=headers).json()

        assert history == []

    def test_a_successful_refinement_appears_with_its_resulting_version(
        self, client, db_session, fake_ai_provider
    ) -> None:
        headers = _headers(client)
        prototype_id = _generated_prototype(client, db_session, headers)

        client.post(
            f"/api/prototypes/{prototype_id}/refine", json={"instruction": "deixa mais premium"}, headers=headers
        )

        history = client.get(f"/api/prototypes/{prototype_id}/refinements", headers=headers).json()

        assert len(history) == 1
        entry = history[0]
        assert entry["instruction"] == "deixa mais premium"
        assert entry["status"] == "succeeded"
        assert entry["error_message"] is None
        assert entry["version_number"] == 2
        assert entry["version_id"] is not None

    def test_a_failed_refinement_appears_without_a_version(
        self, client, db_session, monkeypatch, fake_ai_provider
    ) -> None:
        """Achado/decisão do Prompt 13: um refinamento que FALHOU também
        vira uma "mensagem" no chat (a resposta é o erro, não uma versão
        nova) — nunca fica invisível só porque não produziu uma
        `PrototypeVersion`. Usa `fake_ai_provider` para a geração inicial
        (precisa suceder) e sobrescreve o provider só para a chamada de
        refinamento em si, que deve falhar."""
        headers = _headers(client)
        prototype_id = _generated_prototype(client, db_session, headers)

        from app.domains.briefing.providers.errors import ProviderUnavailableError

        failing_provider = FakeGenerationProvider(error=ProviderUnavailableError("sem chave"))
        monkeypatch.setattr(
            "app.domains.prototypes.generation.service.get_generation_provider", lambda settings: failing_provider
        )
        client.post(
            f"/api/prototypes/{prototype_id}/refine", json={"instruction": "pedido que vai falhar"}, headers=headers
        )

        history = client.get(f"/api/prototypes/{prototype_id}/refinements", headers=headers).json()

        assert len(history) == 1
        entry = history[0]
        assert entry["instruction"] == "pedido que vai falhar"
        assert entry["status"] == "failed"
        assert entry["error_message"] is not None
        assert entry["version_id"] is None
        assert entry["version_number"] is None

    def test_history_is_ordered_oldest_first(self, client, db_session, fake_ai_provider) -> None:
        headers = _headers(client)
        prototype_id = _generated_prototype(client, db_session, headers)

        client.post(f"/api/prototypes/{prototype_id}/refine", json={"instruction": "primeiro pedido"}, headers=headers)
        client.post(f"/api/prototypes/{prototype_id}/refine", json={"instruction": "segundo pedido"}, headers=headers)

        history = client.get(f"/api/prototypes/{prototype_id}/refinements", headers=headers).json()

        assert [h["instruction"] for h in history] == ["primeiro pedido", "segundo pedido"]

    def test_listing_refinements_of_a_prototype_i_dont_have_access_to_returns_404(
        self, client, db_session, fake_ai_provider
    ) -> None:
        owner_headers = _headers(client, "dono3@example.com")
        prototype_id = _generated_prototype(client, db_session, owner_headers)

        other_headers = _headers(client, "outro3@example.com")
        response = client.get(f"/api/prototypes/{prototype_id}/refinements", headers=other_headers)
        assert response.status_code == 404

    def test_listing_refinements_without_token_is_unauthorized(self, client, db_session, fake_ai_provider) -> None:
        headers = _headers(client)
        prototype_id = _generated_prototype(client, db_session, headers)

        response = client.get(f"/api/prototypes/{prototype_id}/refinements")
        assert response.status_code == 401
