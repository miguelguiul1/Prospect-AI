"""Testes de `POST /api/prototypes/{id}/refine`,
`GET /api/prototypes/{id}/versions`,
`GET /api/prototypes/{id}/versions/{version_id}` e
`POST /api/prototypes/{id}/versions/{version_id}/restore` (Fase 9 /
Prompt 12). Mesmo padrão de `test_generation_api.py`: sem
`ANTHROPIC_API_KEY` no ambiente de teste, sempre `FakeGenerationProvider`
injetado."""
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
    """Cria Company + Opportunity + Prototype e roda a geração inicial
    (necessária para o precondition de refinamento) — retorna prototype_id."""
    company = _company_with_context(db)
    client.post("/api/crm/opportunities", json={"company_id": str(company.id)}, headers=headers)
    created = client.post(
        "/api/prototypes", json={"name": "Site", "company_id": str(company.id)}, headers=headers
    ).json()
    prototype_id = created["id"]
    generated = client.post(f"/api/prototypes/{prototype_id}/generate", headers=headers).json()
    assert generated["status"] == "succeeded"
    return prototype_id


class TestRefinePrototype:
    def test_successful_refinement_returns_succeeded_and_updates_components(
        self, client, db_session, fake_ai_provider
    ) -> None:
        headers = _headers(client)
        prototype_id = _generated_prototype(client, db_session, headers)

        response = client.post(
            f"/api/prototypes/{prototype_id}/refine",
            json={"instruction": "deixa mais premium"},
            headers=headers,
        )

        assert response.status_code == 202
        body = response.json()
        assert body["status"] == "succeeded"
        assert body["instruction"] == "deixa mais premium"
        assert body["based_on_version_number"] == 1

    def test_refining_without_a_prior_successful_generation_returns_409(
        self, client, db_session, fake_ai_provider
    ) -> None:
        headers = _headers(client)
        company = _company_with_context(db_session)
        client.post("/api/crm/opportunities", json={"company_id": str(company.id)}, headers=headers)
        created = client.post(
            "/api/prototypes", json={"name": "Site", "company_id": str(company.id)}, headers=headers
        ).json()

        response = client.post(
            f"/api/prototypes/{created['id']}/refine", json={"instruction": "muda algo"}, headers=headers
        )

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "no_previous_version"

    def test_refining_while_a_generation_is_pending_returns_409(
        self, client, db_session, fake_ai_provider
    ) -> None:
        headers = _headers(client)
        prototype_id = _generated_prototype(client, db_session, headers)

        from app.domains.prototypes.models import GenerationRun, GenerationStatus

        db_session.add(
            GenerationRun(
                prototype_id=uuid.UUID(prototype_id),
                company_id=uuid.UUID(
                    client.get(f"/api/prototypes/{prototype_id}", headers=headers).json()["company_id"]
                ),
                status=GenerationStatus.PENDING,
                prompt_version="v1",
                context_version="v1",
            )
        )
        db_session.commit()

        response = client.post(
            f"/api/prototypes/{prototype_id}/refine", json={"instruction": "muda algo"}, headers=headers
        )

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "generation_in_progress"

    def test_refine_without_token_is_unauthorized(self, client, db_session, fake_ai_provider) -> None:
        headers = _headers(client)
        prototype_id = _generated_prototype(client, db_session, headers)

        response = client.post(f"/api/prototypes/{prototype_id}/refine", json={"instruction": "x"})
        assert response.status_code == 401

    def test_refining_a_prototype_i_dont_have_access_to_returns_404(
        self, client, db_session, fake_ai_provider
    ) -> None:
        owner_headers = _headers(client, "dono@example.com")
        prototype_id = _generated_prototype(client, db_session, owner_headers)

        other_headers = _headers(client, "outro@example.com")
        response = client.post(
            f"/api/prototypes/{prototype_id}/refine", json={"instruction": "x"}, headers=other_headers
        )
        assert response.status_code == 404

    def test_empty_instruction_is_rejected(self, client, db_session, fake_ai_provider) -> None:
        headers = _headers(client)
        prototype_id = _generated_prototype(client, db_session, headers)

        response = client.post(f"/api/prototypes/{prototype_id}/refine", json={"instruction": ""}, headers=headers)
        assert response.status_code == 422


class TestCostControlSharedWithGeneration:
    def test_generate_and_refine_use_the_same_daily_rate_limit_key(
        self, client, db_session, monkeypatch, fake_ai_provider
    ) -> None:
        """Seção 5 do Prompt 12: refinamentos contam para o MESMO limite
        diário de geração — provado aqui verificando que os dois
        endpoints incrementam exatamente a mesma chave, não um balde
        separado que dobraria o limite real por dia.

        Não usa `monkeypatch.undo()` (como `test_generation_api.py::
        TestRateLimiting` faz) porque isso desfaria TODOS os patches
        aplicados por este `monkeypatch`, incluindo o do fixture
        `fake_ai_provider` (mesma instância de `monkeypatch` por trás dos
        dois) — sobrescrever `check_and_increment` de novo, por cima do
        bypass autouse, é suficiente e não tem esse efeito colateral."""
        calls: list[str] = []

        def _fake_check(key: str, **kwargs) -> bool:
            calls.append(key)
            return True

        monkeypatch.setattr("app.api.routes.prototypes.check_and_increment", _fake_check)
        headers = _headers(client)
        prototype_id = _generated_prototype(client, db_session, headers)
        calls.clear()  # ignora a chamada de /generate feita dentro de _generated_prototype

        client.post(f"/api/prototypes/{prototype_id}/generate", headers=headers)
        client.post(f"/api/prototypes/{prototype_id}/refine", json={"instruction": "x"}, headers=headers)

        assert len(calls) == 2
        assert calls[0] == calls[1]


class TestListAndGetVersions:
    def test_list_versions_returns_newest_first_with_a_description(
        self, client, db_session, fake_ai_provider
    ) -> None:
        headers = _headers(client)
        prototype_id = _generated_prototype(client, db_session, headers)
        client.post(f"/api/prototypes/{prototype_id}/refine", json={"instruction": "deixa mais premium"}, headers=headers)

        response = client.get(f"/api/prototypes/{prototype_id}/versions", headers=headers)

        assert response.status_code == 200
        versions = response.json()
        assert len(versions) == 2
        assert versions[0]["version_number"] == 2
        assert versions[0]["description"] == "deixa mais premium"
        assert versions[1]["version_number"] == 1
        assert versions[1]["description"] == "Geração inicial por IA"

    def test_get_version_detail_includes_full_component_tree(self, client, db_session, fake_ai_provider) -> None:
        headers = _headers(client)
        prototype_id = _generated_prototype(client, db_session, headers)
        versions = client.get(f"/api/prototypes/{prototype_id}/versions", headers=headers).json()
        version_id = versions[0]["id"]

        response = client.get(f"/api/prototypes/{prototype_id}/versions/{version_id}", headers=headers)

        assert response.status_code == 200
        body = response.json()
        assert body["version_number"] == 1
        assert len(body["components"]) > 0

    def test_get_unknown_version_returns_404(self, client, db_session, fake_ai_provider) -> None:
        headers = _headers(client)
        prototype_id = _generated_prototype(client, db_session, headers)

        response = client.get(f"/api/prototypes/{prototype_id}/versions/{uuid.uuid4()}", headers=headers)
        assert response.status_code == 404

    def test_listing_versions_of_a_prototype_i_dont_have_access_to_returns_404(
        self, client, db_session, fake_ai_provider
    ) -> None:
        owner_headers = _headers(client, "dono2@example.com")
        prototype_id = _generated_prototype(client, db_session, owner_headers)

        other_headers = _headers(client, "outro2@example.com")
        response = client.get(f"/api/prototypes/{prototype_id}/versions", headers=other_headers)
        assert response.status_code == 404


class TestRestoreVersion:
    def test_restore_creates_a_new_version_identical_to_the_old_one(
        self, client, db_session, fake_ai_provider
    ) -> None:
        headers = _headers(client)
        prototype_id = _generated_prototype(client, db_session, headers)
        v1 = client.get(f"/api/prototypes/{prototype_id}/versions", headers=headers).json()[0]

        client.post(f"/api/prototypes/{prototype_id}/refine", json={"instruction": "muda tudo"}, headers=headers)

        response = client.post(
            f"/api/prototypes/{prototype_id}/versions/{v1['id']}/restore", headers=headers
        )

        assert response.status_code == 200
        body = response.json()
        assert body["version_number"] == 3  # geração inicial + refinamento + restauração
        assert body["restored_from_version_number"] == 1
        assert body["description"] == "Restaurado da versão 1"

        reloaded = client.get(f"/api/prototypes/{prototype_id}", headers=headers).json()
        assert reloaded["components"] == body["components"]  # protótipo "atual" agora é a versão restaurada

        history = client.get(f"/api/prototypes/{prototype_id}/versions", headers=headers).json()
        assert len(history) == 3  # nunca apaga histórico

    def test_restore_never_calls_the_ai_provider(self, client, db_session, fake_ai_provider) -> None:
        headers = _headers(client)
        prototype_id = _generated_prototype(client, db_session, headers)
        v1 = client.get(f"/api/prototypes/{prototype_id}/versions", headers=headers).json()[0]
        fake_ai_provider.last_call = None

        client.post(f"/api/prototypes/{prototype_id}/versions/{v1['id']}/restore", headers=headers)

        assert fake_ai_provider.last_call is None

    def test_restore_of_unknown_version_returns_404(self, client, db_session, fake_ai_provider) -> None:
        headers = _headers(client)
        prototype_id = _generated_prototype(client, db_session, headers)

        response = client.post(
            f"/api/prototypes/{prototype_id}/versions/{uuid.uuid4()}/restore", headers=headers
        )
        assert response.status_code == 404
