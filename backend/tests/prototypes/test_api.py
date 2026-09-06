"""Testes de `POST/GET/PUT/DELETE /api/prototypes` e do catálogo de
componentes."""
from __future__ import annotations

import uuid


def test_component_types_catalog_matches_the_validation_allowlist(client) -> None:
    from app.domains.prototypes.schemas import COMPONENT_TYPES

    response = client.get("/api/prototypes/meta/component-types")

    assert response.status_code == 200
    body = response.json()
    assert {item["type"] for item in body} == set(COMPONENT_TYPES)


def test_create_prototype(client) -> None:
    response = client.post("/api/prototypes", json={"name": "Site do cliente X", "description": "Landing page simples"})

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Site do cliente X"
    assert body["components"] == []


def test_create_prototype_requires_a_name(client) -> None:
    response = client.post("/api/prototypes", json={"description": "sem nome"})
    assert response.status_code == 422


def test_get_unknown_prototype_returns_404(client) -> None:
    response = client.get(f"/api/prototypes/{uuid.uuid4()}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "prototype_not_found"


def test_list_prototypes(client) -> None:
    client.post("/api/prototypes", json={"name": "A"})
    client.post("/api/prototypes", json={"name": "B"})

    response = client.get("/api/prototypes")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert len(body["items"]) == 2


def test_update_prototype_components(client) -> None:
    created = client.post("/api/prototypes", json={"name": "Editável"}).json()

    tree = [
        {"id": "root", "type": "container", "parent_id": None, "order": 0, "props": {}, "styles": {}},
        {"id": "txt", "type": "text", "parent_id": "root", "order": 0, "props": {"content": "Olá mundo"}, "styles": {}},
    ]
    response = client.put(f"/api/prototypes/{created['id']}", json={"components": tree})

    assert response.status_code == 200
    body = response.json()
    assert len(body["components"]) == 2
    assert body["components"][1]["props"]["content"] == "Olá mundo"


def test_update_with_unknown_component_type_returns_422(client) -> None:
    created = client.post("/api/prototypes", json={"name": "Vai falhar"}).json()

    bad_tree = [{"id": "a", "type": "script", "parent_id": None, "order": 0}]
    response = client.put(f"/api/prototypes/{created['id']}", json={"components": bad_tree})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_component_tree"


def test_update_unknown_prototype_returns_404(client) -> None:
    response = client.put(f"/api/prototypes/{uuid.uuid4()}", json={"name": "X"})
    assert response.status_code == 404


def test_delete_prototype(client) -> None:
    created = client.post("/api/prototypes", json={"name": "Para excluir"}).json()

    response = client.delete(f"/api/prototypes/{created['id']}")
    assert response.status_code == 204

    response = client.get(f"/api/prototypes/{created['id']}")
    assert response.status_code == 404


def test_delete_unknown_prototype_returns_404(client) -> None:
    response = client.delete(f"/api/prototypes/{uuid.uuid4()}")
    assert response.status_code == 404


def test_full_lifecycle_create_update_reload(client) -> None:
    created = client.post("/api/prototypes", json={"name": "Ciclo completo"}).json()
    tree = [{"id": "a", "type": "heading", "parent_id": None, "order": 0, "props": {"content": "Título"}, "styles": {}}]

    client.put(f"/api/prototypes/{created['id']}", json={"components": tree})
    reloaded = client.get(f"/api/prototypes/{created['id']}").json()

    assert reloaded["components"][0]["props"]["content"] == "Título"
