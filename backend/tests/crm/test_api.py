"""Testes de API do CRM (Fase 7) — fluxo completo através do `client` real
(registro -> login -> uso do token), nunca com `get_current_user` sobrescrita:
isto exercita a autenticação de verdade em cada chamada, não um atalho de
teste."""
from __future__ import annotations

from app.domains.companies.models import Company


def _auth_headers(client, email: str = "vendedor@example.com") -> dict:
    response = client.post("/api/auth/register", json={"email": email, "name": "Vendedor", "password": "senhaforte123"})
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _company(db, name: str = "Empresa Teste") -> Company:
    company = Company(canonical_name=name)
    db.add(company)
    db.flush()
    db.commit()
    return company


class TestOpportunitiesRequireAuth:
    def test_list_without_token_is_unauthorized(self, client) -> None:
        assert client.get("/api/crm/opportunities").status_code == 401

    def test_create_without_token_is_unauthorized(self, client, db_session) -> None:
        company = _company(db_session)
        response = client.post("/api/crm/opportunities", json={"company_id": str(company.id)})
        assert response.status_code == 401


class TestCreateOpportunity:
    def test_creates_and_returns_summary(self, client, db_session) -> None:
        headers = _auth_headers(client)
        company = _company(db_session)

        response = client.post("/api/crm/opportunities", json={"company_id": str(company.id)}, headers=headers)

        assert response.status_code == 201
        body = response.json()
        assert body["company_name"] == "Empresa Teste"
        assert body["stage"]["key"] == "new"
        assert body["status"] == "open"

    def test_creating_twice_for_the_same_company_is_idempotent(self, client, db_session) -> None:
        headers = _auth_headers(client)
        company = _company(db_session)

        first = client.post("/api/crm/opportunities", json={"company_id": str(company.id)}, headers=headers)
        second = client.post("/api/crm/opportunities", json={"company_id": str(company.id)}, headers=headers)

        assert first.json()["id"] == second.json()["id"]

    def test_unknown_company_returns_404(self, client) -> None:
        headers = _auth_headers(client)
        response = client.post(
            "/api/crm/opportunities", json={"company_id": "00000000-0000-0000-0000-000000000000"}, headers=headers
        )
        assert response.status_code == 404

    def test_second_user_gets_conflict_not_the_first_users_data(self, client, db_session) -> None:
        """Nunca vaza dados de Opportunity de outro usuário através de
        `create_or_get` (Prompt 11, seção 4.3 — IDOR por um caminho
        diferente do GET direto)."""
        headers_a = _auth_headers(client, email="a@example.com")
        headers_b = _auth_headers(client, email="b@example.com")
        company = _company(db_session)

        client.post("/api/crm/opportunities", json={"company_id": str(company.id)}, headers=headers_a)
        response = client.post("/api/crm/opportunities", json={"company_id": str(company.id)}, headers=headers_b)

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "opportunity_owned_by_another_user"


class TestPipelineAndKpis:
    def test_pipeline_board_groups_by_stage(self, client, db_session) -> None:
        headers = _auth_headers(client)
        company = _company(db_session)
        client.post("/api/crm/opportunities", json={"company_id": str(company.id)}, headers=headers)

        response = client.get("/api/crm/pipeline", headers=headers)

        assert response.status_code == 200
        columns = response.json()["columns"]
        assert len(columns) == 8
        new_column = next(c for c in columns if c["stage"]["key"] == "new")
        assert len(new_column["opportunities"]) == 1

    def test_kpis_reflect_open_opportunities(self, client, db_session) -> None:
        headers = _auth_headers(client)
        company = _company(db_session)
        client.post("/api/crm/opportunities", json={"company_id": str(company.id)}, headers=headers)

        response = client.get("/api/crm/kpis", headers=headers)

        assert response.status_code == 200
        assert response.json()["open_count"] == 1
        assert response.json()["new_count"] == 1


class TestOpportunityDetailAndStage:
    def test_detail_includes_company_identity(self, client, db_session) -> None:
        headers = _auth_headers(client)
        company = _company(db_session)
        opp_id = client.post("/api/crm/opportunities", json={"company_id": str(company.id)}, headers=headers).json()["id"]

        response = client.get(f"/api/crm/opportunities/{opp_id}", headers=headers)

        assert response.status_code == 200
        body = response.json()
        assert body["company_name"] == "Empresa Teste"
        assert body["contacts"] == []
        assert len(body["recent_activities"]) == 1  # "Oportunidade criada"

    def test_change_stage(self, client, db_session) -> None:
        headers = _auth_headers(client)
        company = _company(db_session)
        opp_id = client.post("/api/crm/opportunities", json={"company_id": str(company.id)}, headers=headers).json()["id"]

        response = client.patch(f"/api/crm/opportunities/{opp_id}/stage", json={"stage_key": "meeting"}, headers=headers)

        assert response.status_code == 200
        assert response.json()["stage"]["key"] == "meeting"

    def test_close_and_reopen(self, client, db_session) -> None:
        headers = _auth_headers(client)
        company = _company(db_session)
        opp_id = client.post("/api/crm/opportunities", json={"company_id": str(company.id)}, headers=headers).json()["id"]

        closed = client.post(f"/api/crm/opportunities/{opp_id}/close", json={"outcome": "won"}, headers=headers)
        assert closed.status_code == 200
        assert closed.json()["status"] == "won"

        reopened = client.post(f"/api/crm/opportunities/{opp_id}/reopen", headers=headers)
        assert reopened.status_code == 200
        assert reopened.json()["status"] == "open"

    def test_timeline_grows_with_each_action(self, client, db_session) -> None:
        headers = _auth_headers(client)
        company = _company(db_session)
        opp_id = client.post("/api/crm/opportunities", json={"company_id": str(company.id)}, headers=headers).json()["id"]

        client.patch(f"/api/crm/opportunities/{opp_id}/stage", json={"stage_key": "qualified"}, headers=headers)

        response = client.get(f"/api/crm/opportunities/{opp_id}/timeline", headers=headers)
        assert response.status_code == 200
        assert len(response.json()) == 2  # criação + mudança de etapa


class TestContactsAndActivitiesViaApi:
    def _opportunity(self, client, db_session, headers) -> tuple[str, str]:
        company = _company(db_session)
        opp_id = client.post("/api/crm/opportunities", json={"company_id": str(company.id)}, headers=headers).json()["id"]
        return opp_id, str(company.id)

    def test_create_contact_requires_an_opportunity_for_the_company(self, client, db_session) -> None:
        headers = _auth_headers(client)
        company = _company(db_session)
        response = client.post(
            "/api/crm/contacts",
            json={"company_id": str(company.id), "name": "Fulano", "source": "manual"},
            headers=headers,
        )
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "no_opportunity_for_company"

    def test_create_and_list_contact(self, client, db_session) -> None:
        headers = _auth_headers(client)
        _, company_id = self._opportunity(client, db_session, headers)

        created = client.post(
            "/api/crm/contacts",
            json={"company_id": company_id, "name": "Fulano", "source": "manual"},
            headers=headers,
        )
        assert created.status_code == 201

        listed = client.get(f"/api/crm/contacts?company_id={company_id}", headers=headers)
        assert listed.status_code == 200
        assert len(listed.json()) == 1

    def test_create_activity_note(self, client, db_session) -> None:
        headers = _auth_headers(client)
        opp_id, _ = self._opportunity(client, db_session, headers)

        response = client.post(
            "/api/crm/activities",
            json={"opportunity_id": opp_id, "type": "note", "description": "Ligou e pediu proposta"},
            headers=headers,
        )
        assert response.status_code == 201
        assert response.json()["type"] == "note"

    def test_cannot_create_a_stage_change_activity_directly(self, client, db_session) -> None:
        headers = _auth_headers(client)
        opp_id, _ = self._opportunity(client, db_session, headers)

        response = client.post(
            "/api/crm/activities",
            json={"opportunity_id": opp_id, "type": "stage_change", "description": "forjado"},
            headers=headers,
        )
        assert response.status_code == 422

    def test_task_lifecycle(self, client, db_session) -> None:
        headers = _auth_headers(client)
        opp_id, _ = self._opportunity(client, db_session, headers)

        created = client.post(
            "/api/crm/activities",
            json={"opportunity_id": opp_id, "type": "task", "title": "Follow-up"},
            headers=headers,
        )
        activity_id = created.json()["id"]
        assert created.json()["status"] == "open"

        completed = client.put(f"/api/crm/activities/{activity_id}", json={"completed": True}, headers=headers)
        assert completed.json()["status"] == "done"

    def test_note_html_is_rejected(self, client, db_session) -> None:
        headers = _auth_headers(client)
        opp_id, _ = self._opportunity(client, db_session, headers)

        response = client.post(
            "/api/crm/activities",
            json={"opportunity_id": opp_id, "type": "note", "description": "<script>alert(1)</script>"},
            headers=headers,
        )
        assert response.status_code == 422
