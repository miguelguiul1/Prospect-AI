"""Testes da API HTTP do Discovery.

Nenhuma chamada real ao Google acontece aqui: o teste do "caminho feliz"
substitui o provider por um fake via monkeypatch no registro
(`app.domains.discovery.providers`); o teste "sem API key" usa
deliberadamente a configuração real de teste (sem `GOOGLE_MAPS_API_KEY`)
para provar o critério de conclusão "execução sem API key falha de forma
controlada" fim-a-fim pela própria API.
"""
from __future__ import annotations

import app.domains.discovery.providers as providers_module
from app.domains.discovery.dto import DiscoveredCompany
from app.domains.discovery.providers.base import DiscoveryProvider, ProviderPage


class _FakeProvider(DiscoveryProvider):
    name = "google_places"

    def is_configured(self) -> bool:
        return True

    def search(self, query, *, page_token: str | None = None) -> ProviderPage:
        result = DiscoveredCompany(
            source="google_places",
            external_id="ChIJ_api_test",
            name="Empresa via API",
            website="https://empresa-api.example.com",
        )
        return ProviderPage(results=[result], raw_result_count=1, operation="searchText")


VALID_PAYLOAD = {"region": "Interlagos", "city": "São Paulo", "category": "restaurantes"}


def test_search_without_api_key_fails_in_a_controlled_way(client) -> None:
    """Sem GOOGLE_MAPS_API_KEY configurada (o padrão neste ambiente de
    teste — ver test_config.py), a busca não deve derrubar a API: o
    SearchRun é criado e marcado como falho, com erro explícito."""
    response = client.post("/api/discovery/search", json=VALID_PAYLOAD)

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "failed"
    assert body["error_message"] is not None
    assert body["persisted_count"] is None or body["persisted_count"] == 0


def test_search_happy_path_persists_via_fake_provider(client, monkeypatch) -> None:
    monkeypatch.setitem(providers_module._PROVIDER_FACTORIES, "google_places", lambda settings: _FakeProvider())

    response = client.post("/api/discovery/search", json=VALID_PAYLOAD)

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "completed"
    assert body["persisted_count"] == 1
    assert body["new_company_count"] == 1
    assert body["execution_mode"] == "executed_sync"  # sem Redis disponível neste ambiente

    run_id = body["id"]
    get_response = client.get(f"/api/discovery/runs/{run_id}")
    assert get_response.status_code == 200
    assert get_response.json()["status"] == "completed"
    assert get_response.json()["persisted_count"] == 1


def test_get_unknown_run_returns_404(client) -> None:
    response = client.get("/api/discovery/runs/00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "search_run_not_found"


def test_invalid_payload_returns_422(client) -> None:
    response = client.post("/api/discovery/search", json={"region": "Interlagos", "category": "   "})

    assert response.status_code == 422


def test_payload_without_geography_or_region_is_rejected(client) -> None:
    response = client.post("/api/discovery/search", json={"category": "restaurantes"})

    assert response.status_code == 422


def test_search_run_returns_normalized_parameters(client, monkeypatch) -> None:
    monkeypatch.setitem(providers_module._PROVIDER_FACTORIES, "google_places", lambda settings: _FakeProvider())

    response = client.post(
        "/api/discovery/search",
        json={"region": "  Interlagos  ", "category": "  Restaurantes  "},
    )

    parameters = response.json()["parameters"]
    assert parameters["region"] == "Interlagos"
    assert parameters["category"] == "Restaurantes"
