"""Testes de `POST/GET/PUT/DELETE /api/prototypes` e do catálogo de
componentes (Prompt 10: autenticação + vínculo com Company obrigatórios)."""
from __future__ import annotations

import uuid

from app.domains.companies.models import Company


def _auth_headers(client, email: str = "vendedor@example.com") -> dict:
    response = client.post(
        "/api/auth/register", json={"email": email, "name": "Vendedor", "password": "senhaforte123"}
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _company(db, name: str = "Empresa Teste") -> Company:
    company = Company(canonical_name=name)
    db.add(company)
    db.flush()
    db.commit()
    return company


def _company_with_opportunity(client, db, headers: dict, name: str = "Empresa Teste") -> Company:
    """Cria uma Company e uma Opportunity aberta para ela, do usuário dono
    de `headers` — o pré-requisito de acesso a Prototype (ver
    `app.domains.prototypes.authorization`)."""
    company = _company(db, name)
    client.post("/api/crm/opportunities", json={"company_id": str(company.id)}, headers=headers)
    return company


def test_component_types_catalog_matches_the_validation_allowlist(client) -> None:
    from app.domains.prototypes.schemas import COMPONENT_TYPES

    response = client.get("/api/prototypes/meta/component-types")

    assert response.status_code == 200
    body = response.json()
    assert {item["type"] for item in body} == set(COMPONENT_TYPES)


class TestRequiresAuth:
    def test_list_without_token_is_unauthorized(self, client) -> None:
        assert client.get("/api/prototypes").status_code == 401

    def test_create_without_token_is_unauthorized(self, client, db_session) -> None:
        company = _company(db_session)
        response = client.post(
            "/api/prototypes", json={"name": "X", "company_id": str(company.id)}
        )
        assert response.status_code == 401


class TestCreatePrototype:
    def test_create_requires_a_company_with_an_opportunity(self, client, db_session) -> None:
        headers = _auth_headers(client)
        company = _company_with_opportunity(client, db_session, headers)

        response = client.post(
            "/api/prototypes",
            json={"name": "Site do cliente X", "description": "Landing page simples", "company_id": str(company.id)},
            headers=headers,
        )

        assert response.status_code == 201
        body = response.json()
        assert body["name"] == "Site do cliente X"
        assert body["company_id"] == str(company.id)
        assert body["components"] == []

    def test_create_requires_a_name(self, client, db_session) -> None:
        headers = _auth_headers(client)
        company = _company_with_opportunity(client, db_session, headers)

        response = client.post(
            "/api/prototypes", json={"description": "sem nome", "company_id": str(company.id)}, headers=headers
        )
        assert response.status_code == 422

    def test_create_requires_a_company_id(self, client) -> None:
        headers = _auth_headers(client)
        response = client.post("/api/prototypes", json={"name": "Sem empresa"}, headers=headers)
        assert response.status_code == 422

    def test_create_for_unknown_company_returns_404(self, client) -> None:
        headers = _auth_headers(client)
        response = client.post(
            "/api/prototypes",
            json={"name": "X", "company_id": "00000000-0000-0000-0000-000000000000"},
            headers=headers,
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "company_not_found"

    def test_create_for_a_company_i_have_no_opportunity_for_returns_404_not_403(
        self, client, db_session
    ) -> None:
        """Mesmo padrão de IDOR do resto do CRM: nunca 403 (que confirmaria
        que a empresa existe), sempre 404."""
        headers = _auth_headers(client)
        company = _company(db_session, "Empresa sem Opportunity")

        response = client.post(
            "/api/prototypes", json={"name": "X", "company_id": str(company.id)}, headers=headers
        )

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "company_not_found"


class TestGetPrototype:
    def test_get_unknown_prototype_returns_404(self, client) -> None:
        headers = _auth_headers(client)
        response = client.get(f"/api/prototypes/{uuid.uuid4()}", headers=headers)
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "prototype_not_found"

    def test_get_prototype_of_a_company_i_dont_have_access_to_returns_404(self, client, db_session) -> None:
        """Prompt 10, seção 1: acesso a Prototype de uma Company que não é
        minha deve dar 404, nunca 403."""
        owner_headers = _auth_headers(client, email="dono@example.com")
        company = _company_with_opportunity(client, db_session, owner_headers)
        created = client.post(
            "/api/prototypes", json={"name": "Do dono", "company_id": str(company.id)}, headers=owner_headers
        ).json()

        other_headers = _auth_headers(client, email="outro@example.com")
        response = client.get(f"/api/prototypes/{created['id']}", headers=other_headers)

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "prototype_not_found"

    def test_get_own_prototype_succeeds(self, client, db_session) -> None:
        headers = _auth_headers(client)
        company = _company_with_opportunity(client, db_session, headers)
        created = client.post(
            "/api/prototypes", json={"name": "Meu", "company_id": str(company.id)}, headers=headers
        ).json()

        response = client.get(f"/api/prototypes/{created['id']}", headers=headers)
        assert response.status_code == 200
        assert response.json()["id"] == created["id"]


class TestListPrototypes:
    def test_list_only_shows_prototypes_of_accessible_companies(self, client, db_session) -> None:
        headers_a = _auth_headers(client, email="a@example.com")
        headers_b = _auth_headers(client, email="b@example.com")
        company_a = _company_with_opportunity(client, db_session, headers_a, "Empresa A")
        company_b = _company_with_opportunity(client, db_session, headers_b, "Empresa B")

        client.post("/api/prototypes", json={"name": "A1", "company_id": str(company_a.id)}, headers=headers_a)
        client.post("/api/prototypes", json={"name": "B1", "company_id": str(company_b.id)}, headers=headers_b)

        response = client.get("/api/prototypes", headers=headers_a)

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert body["items"][0]["name"] == "A1"


class TestUpdatePrototype:
    def test_update_prototype_components(self, client, db_session) -> None:
        headers = _auth_headers(client)
        company = _company_with_opportunity(client, db_session, headers)
        created = client.post(
            "/api/prototypes", json={"name": "Editável", "company_id": str(company.id)}, headers=headers
        ).json()

        tree = [
            {"id": "root", "type": "container", "parent_id": None, "order": 0, "props": {}, "styles": {}},
            {"id": "txt", "type": "text", "parent_id": "root", "order": 0, "props": {"content": "Olá mundo"}, "styles": {}},
        ]
        response = client.put(f"/api/prototypes/{created['id']}", json={"components": tree}, headers=headers)

        assert response.status_code == 200
        body = response.json()
        assert len(body["components"]) == 2
        assert body["components"][1]["props"]["content"] == "Olá mundo"

    def test_update_with_unknown_component_type_returns_422(self, client, db_session) -> None:
        headers = _auth_headers(client)
        company = _company_with_opportunity(client, db_session, headers)
        created = client.post(
            "/api/prototypes", json={"name": "Vai falhar", "company_id": str(company.id)}, headers=headers
        ).json()

        bad_tree = [{"id": "a", "type": "script", "parent_id": None, "order": 0}]
        response = client.put(f"/api/prototypes/{created['id']}", json={"components": bad_tree}, headers=headers)

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "invalid_component_tree"

    def test_update_unknown_prototype_returns_404(self, client) -> None:
        headers = _auth_headers(client)
        response = client.put(f"/api/prototypes/{uuid.uuid4()}", json={"name": "X"}, headers=headers)
        assert response.status_code == 404

    def test_update_prototype_of_a_company_i_dont_have_access_to_returns_404(self, client, db_session) -> None:
        owner_headers = _auth_headers(client, email="dono2@example.com")
        company = _company_with_opportunity(client, db_session, owner_headers)
        created = client.post(
            "/api/prototypes", json={"name": "Do dono", "company_id": str(company.id)}, headers=owner_headers
        ).json()

        other_headers = _auth_headers(client, email="outro2@example.com")
        response = client.put(f"/api/prototypes/{created['id']}", json={"name": "Invadido"}, headers=other_headers)

        assert response.status_code == 404


class TestDeletePrototype:
    def test_delete_prototype(self, client, db_session) -> None:
        headers = _auth_headers(client)
        company = _company_with_opportunity(client, db_session, headers)
        created = client.post(
            "/api/prototypes", json={"name": "Para excluir", "company_id": str(company.id)}, headers=headers
        ).json()

        response = client.delete(f"/api/prototypes/{created['id']}", headers=headers)
        assert response.status_code == 204

        response = client.get(f"/api/prototypes/{created['id']}", headers=headers)
        assert response.status_code == 404

    def test_delete_unknown_prototype_returns_404(self, client) -> None:
        headers = _auth_headers(client)
        response = client.delete(f"/api/prototypes/{uuid.uuid4()}", headers=headers)
        assert response.status_code == 404

    def test_delete_prototype_of_a_company_i_dont_have_access_to_returns_404(self, client, db_session) -> None:
        owner_headers = _auth_headers(client, email="dono3@example.com")
        company = _company_with_opportunity(client, db_session, owner_headers)
        created = client.post(
            "/api/prototypes", json={"name": "Do dono", "company_id": str(company.id)}, headers=owner_headers
        ).json()

        other_headers = _auth_headers(client, email="outro3@example.com")
        response = client.delete(f"/api/prototypes/{created['id']}", headers=other_headers)

        assert response.status_code == 404


def test_full_lifecycle_create_update_reload(client, db_session) -> None:
    headers = _auth_headers(client)
    company = _company_with_opportunity(client, db_session, headers)
    created = client.post(
        "/api/prototypes", json={"name": "Ciclo completo", "company_id": str(company.id)}, headers=headers
    ).json()
    tree = [{"id": "a", "type": "heading", "parent_id": None, "order": 0, "props": {"content": "Título"}, "styles": {}}]

    client.put(f"/api/prototypes/{created['id']}", json={"components": tree}, headers=headers)
    reloaded = client.get(f"/api/prototypes/{created['id']}", headers=headers).json()

    assert reloaded["components"][0]["props"]["content"] == "Título"
