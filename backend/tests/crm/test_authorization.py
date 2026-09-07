"""Testes de autorização / IDOR do CRM (Fase 7).

Prompt 11, seção 4.3: "Usuário A tenta acessar Opportunity do Usuário B" ->
"acesso negado", para GET/PUT/PATCH/DELETE/activities/contacts/outreach.
Todo caso aqui espera 404 (nunca 403) — ver `app.domains.crm.authorization`
para a justificativa de nunca revelar que o recurso existe.
"""
from __future__ import annotations

from app.domains.companies.models import Company


def _register(client, email: str) -> dict:
    headers = {}
    token = client.post(
        "/api/auth/register", json={"email": email, "name": "Usuário", "password": "senhaforte123"}
    ).json()["access_token"]
    headers["Authorization"] = f"Bearer {token}"
    return headers


def _company(db, name: str = "Empresa Alvo") -> Company:
    company = Company(canonical_name=name)
    db.add(company)
    db.flush()
    db.commit()
    return company


class TestOpportunityIDOR:
    def _setup(self, client, db_session):
        headers_a = _register(client, "a@example.com")
        headers_b = _register(client, "b@example.com")
        company = _company(db_session)
        opp_id = client.post("/api/crm/opportunities", json={"company_id": str(company.id)}, headers=headers_a).json()["id"]
        return headers_a, headers_b, opp_id

    def test_get_by_another_user_is_not_found(self, client, db_session) -> None:
        _, headers_b, opp_id = self._setup(client, db_session)
        response = client.get(f"/api/crm/opportunities/{opp_id}", headers=headers_b)
        assert response.status_code == 404

    def test_stage_change_by_another_user_is_not_found(self, client, db_session) -> None:
        _, headers_b, opp_id = self._setup(client, db_session)
        response = client.patch(f"/api/crm/opportunities/{opp_id}/stage", json={"stage_key": "won"}, headers=headers_b)
        assert response.status_code == 404

    def test_owner_change_by_another_user_is_not_found(self, client, db_session) -> None:
        _, headers_b, opp_id = self._setup(client, db_session)
        response = client.patch(
            f"/api/crm/opportunities/{opp_id}/owner",
            json={"owner_id": "00000000-0000-0000-0000-000000000000"},
            headers=headers_b,
        )
        assert response.status_code == 404

    def test_close_by_another_user_is_not_found(self, client, db_session) -> None:
        _, headers_b, opp_id = self._setup(client, db_session)
        response = client.post(f"/api/crm/opportunities/{opp_id}/close", json={"outcome": "won"}, headers=headers_b)
        assert response.status_code == 404

    def test_reopen_by_another_user_is_not_found(self, client, db_session) -> None:
        _, headers_b, opp_id = self._setup(client, db_session)
        response = client.post(f"/api/crm/opportunities/{opp_id}/reopen", headers=headers_b)
        assert response.status_code == 404

    def test_timeline_by_another_user_is_not_found(self, client, db_session) -> None:
        _, headers_b, opp_id = self._setup(client, db_session)
        response = client.get(f"/api/crm/opportunities/{opp_id}/timeline", headers=headers_b)
        assert response.status_code == 404

    def test_the_owner_can_still_access_normally(self, client, db_session) -> None:
        headers_a, _, opp_id = self._setup(client, db_session)
        response = client.get(f"/api/crm/opportunities/{opp_id}", headers=headers_a)
        assert response.status_code == 200

    def test_a_users_opportunity_never_appears_in_another_users_list(self, client, db_session) -> None:
        headers_a, headers_b, _ = self._setup(client, db_session)
        response = client.get("/api/crm/opportunities", headers=headers_b)
        assert response.json()["items"] == []

    def test_a_users_opportunity_never_appears_in_another_users_pipeline(self, client, db_session) -> None:
        headers_a, headers_b, _ = self._setup(client, db_session)
        response = client.get("/api/crm/pipeline", headers=headers_b)
        for column in response.json()["columns"]:
            assert column["opportunities"] == []


class TestActivityIDOR:
    def _setup(self, client, db_session):
        headers_a = _register(client, "a@example.com")
        headers_b = _register(client, "b@example.com")
        company = _company(db_session)
        opp_id = client.post("/api/crm/opportunities", json={"company_id": str(company.id)}, headers=headers_a).json()["id"]
        activity_id = client.post(
            "/api/crm/activities", json={"opportunity_id": opp_id, "type": "note", "description": "nota A"}, headers=headers_a
        ).json()["id"]
        return headers_a, headers_b, opp_id, activity_id

    def test_creating_an_activity_on_another_users_opportunity_is_not_found(self, client, db_session) -> None:
        _, headers_b, opp_id, _ = self._setup(client, db_session)
        response = client.post(
            "/api/crm/activities", json={"opportunity_id": opp_id, "type": "note", "description": "tentativa"}, headers=headers_b
        )
        assert response.status_code == 404

    def test_editing_another_users_activity_is_not_found(self, client, db_session) -> None:
        _, headers_b, _, activity_id = self._setup(client, db_session)
        response = client.put(f"/api/crm/activities/{activity_id}", json={"completed": True}, headers=headers_b)
        assert response.status_code == 404

    def test_deleting_another_users_activity_is_not_found(self, client, db_session) -> None:
        _, headers_b, _, activity_id = self._setup(client, db_session)
        response = client.delete(f"/api/crm/activities/{activity_id}", headers=headers_b)
        assert response.status_code == 404


class TestContactIDOR:
    def _setup(self, client, db_session):
        headers_a = _register(client, "a@example.com")
        headers_b = _register(client, "b@example.com")
        company = _company(db_session)
        client.post("/api/crm/opportunities", json={"company_id": str(company.id)}, headers=headers_a)
        contact_id = client.post(
            "/api/crm/contacts", json={"company_id": str(company.id), "name": "Contato A", "source": "manual"}, headers=headers_a
        ).json()["id"]
        return headers_a, headers_b, str(company.id), contact_id

    def test_listing_contacts_without_an_opportunity_for_the_company_is_forbidden(self, client, db_session) -> None:
        _, headers_b, company_id, _ = self._setup(client, db_session)
        response = client.get(f"/api/crm/contacts?company_id={company_id}", headers=headers_b)
        assert response.status_code == 403

    def test_updating_a_contact_without_an_opportunity_for_the_company_is_not_found(self, client, db_session) -> None:
        _, headers_b, _, contact_id = self._setup(client, db_session)
        response = client.put(f"/api/crm/contacts/{contact_id}", json={"name": "Hackeado"}, headers=headers_b)
        assert response.status_code == 404

    def test_deleting_a_contact_without_an_opportunity_for_the_company_is_not_found(self, client, db_session) -> None:
        _, headers_b, _, contact_id = self._setup(client, db_session)
        response = client.delete(f"/api/crm/contacts/{contact_id}", headers=headers_b)
        assert response.status_code == 404
