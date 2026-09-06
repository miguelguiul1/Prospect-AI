"""Testes de integração de `PrototypeService` contra o banco real de teste
(SQLite via `db_session`)."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy.orm import Session

from app.domains.prototypes.models import Prototype
from app.domains.prototypes.service import PrototypeService


class TestCreate:
    def test_creates_with_empty_component_tree(self, db_session: Session) -> None:
        service = PrototypeService(db_session)
        prototype = service.create(name="Landing page", description="Ideia inicial")

        assert prototype.id is not None
        assert prototype.name == "Landing page"
        assert prototype.description == "Ideia inicial"
        assert prototype.components == []
        assert prototype.settings == {}

    def test_description_is_optional(self, db_session: Session) -> None:
        service = PrototypeService(db_session)
        prototype = service.create(name="Sem descrição")
        assert prototype.description is None


class TestListGet:
    def test_list_orders_by_most_recently_updated(self, db_session: Session) -> None:
        service = PrototypeService(db_session)
        first = service.create(name="Primeiro")
        second = service.create(name="Segundo")
        service.update(second.id, name="Segundo (editado)")

        page = service.list()

        assert page.total == 2
        assert page.items[0].id == second.id
        assert page.items[1].id == first.id

    def test_get_unknown_returns_none(self, db_session: Session) -> None:
        service = PrototypeService(db_session)
        assert service.get(uuid.uuid4()) is None

    def test_pagination(self, db_session: Session) -> None:
        service = PrototypeService(db_session)
        for i in range(5):
            service.create(name=f"Proto {i}")

        page = service.list(limit=2, offset=2)

        assert page.total == 5
        assert len(page.items) == 2


class TestUpdate:
    def test_update_name_and_description(self, db_session: Session) -> None:
        service = PrototypeService(db_session)
        prototype = service.create(name="Old")

        updated = service.update(prototype.id, name="New", description="Nova descrição")

        assert updated.name == "New"
        assert updated.description == "Nova descrição"

    def test_update_unknown_prototype_raises_lookup_error(self, db_session: Session) -> None:
        service = PrototypeService(db_session)
        with pytest.raises(LookupError):
            service.update(uuid.uuid4(), name="X")

    def test_update_with_valid_components_persists_tree(self, db_session: Session) -> None:
        service = PrototypeService(db_session)
        prototype = service.create(name="Com componentes")

        tree = [
            {"id": "c1", "type": "container", "parent_id": None, "order": 0, "props": {}, "styles": {}},
            {"id": "c2", "type": "text", "parent_id": "c1", "order": 0, "props": {"content": "Olá"}, "styles": {}},
        ]
        updated = service.update(prototype.id, components=tree)

        assert len(updated.components) == 2
        reloaded = db_session.get(Prototype, prototype.id)
        assert len(reloaded.components) == 2
        assert reloaded.components[1]["props"]["content"] == "Olá"

    def test_update_with_invalid_components_raises_value_error_and_does_not_persist(
        self, db_session: Session
    ) -> None:
        service = PrototypeService(db_session)
        prototype = service.create(name="Vai falhar")

        bad_tree = [{"id": "c1", "type": "not-a-real-type", "parent_id": None, "order": 0}]
        with pytest.raises(Exception):
            service.update(prototype.id, components=bad_tree)

        reloaded = db_session.get(Prototype, prototype.id)
        assert reloaded.components == []

    def test_partial_update_does_not_touch_other_fields(self, db_session: Session) -> None:
        service = PrototypeService(db_session)
        prototype = service.create(name="Original", description="Descrição original")

        service.update(prototype.id, name="Só o nome mudou")

        reloaded = db_session.get(Prototype, prototype.id)
        assert reloaded.name == "Só o nome mudou"
        assert reloaded.description == "Descrição original"


class TestDelete:
    def test_delete_existing_returns_true(self, db_session: Session) -> None:
        service = PrototypeService(db_session)
        prototype = service.create(name="Para excluir")

        assert service.delete(prototype.id) is True
        assert db_session.get(Prototype, prototype.id) is None

    def test_delete_unknown_returns_false(self, db_session: Session) -> None:
        service = PrototypeService(db_session)
        assert service.delete(uuid.uuid4()) is False
