"""Testes de integração de `PrototypeService` contra o banco real de teste
(SQLite via `db_session`). Prompt 10: `create` agora exige `company_id` e
verifica que o usuário tem uma Opportunity para a empresa."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy.orm import Session

from app.domains.companies.models import Company
from app.domains.crm.models import Opportunity, OpportunityStatus, PipelineStage
from app.domains.prototypes.models import Prototype
from app.domains.prototypes.service import PrototypeService


def _company(db: Session, name: str = "Empresa Teste") -> Company:
    company = Company(canonical_name=name)
    db.add(company)
    db.flush()
    return company


def _opportunity_for(db: Session, company: Company, owner_id: uuid.UUID) -> Opportunity:
    stage = db.query(PipelineStage).order_by(PipelineStage.order.asc()).first()
    opportunity = Opportunity(company_id=company.id, owner_id=owner_id, stage_id=stage.id, status=OpportunityStatus.OPEN)
    db.add(opportunity)
    db.flush()
    return opportunity


class TestCreate:
    def test_creates_with_empty_component_tree_when_user_owns_the_company(self, db_session: Session) -> None:
        user_id = uuid.uuid4()
        company = _company(db_session)
        _opportunity_for(db_session, company, user_id)

        service = PrototypeService(db_session)
        prototype = service.create(name="Landing page", description="Ideia inicial", company_id=company.id, user_id=user_id)

        assert prototype.id is not None
        assert prototype.company_id == company.id
        assert prototype.name == "Landing page"
        assert prototype.description == "Ideia inicial"
        assert prototype.components == []
        assert prototype.settings == {}

    def test_description_is_optional(self, db_session: Session) -> None:
        user_id = uuid.uuid4()
        company = _company(db_session)
        _opportunity_for(db_session, company, user_id)

        service = PrototypeService(db_session)
        prototype = service.create(name="Sem descrição", description=None, company_id=company.id, user_id=user_id)
        assert prototype.description is None

    def test_unknown_company_raises_lookup_error(self, db_session: Session) -> None:
        service = PrototypeService(db_session)
        with pytest.raises(LookupError):
            service.create(name="X", description=None, company_id=uuid.uuid4(), user_id=uuid.uuid4())

    def test_company_without_an_opportunity_for_this_user_raises_permission_error(self, db_session: Session) -> None:
        company = _company(db_session)  # nenhuma Opportunity criada para ninguém

        service = PrototypeService(db_session)
        with pytest.raises(PermissionError):
            service.create(name="X", description=None, company_id=company.id, user_id=uuid.uuid4())


class TestListForUser:
    def test_only_lists_prototypes_of_companies_the_user_has_an_opportunity_for(self, db_session: Session) -> None:
        user_a, user_b = uuid.uuid4(), uuid.uuid4()
        company_a = _company(db_session, "A")
        company_b = _company(db_session, "B")
        _opportunity_for(db_session, company_a, user_a)
        _opportunity_for(db_session, company_b, user_b)

        service = PrototypeService(db_session)
        service.create(name="A1", description=None, company_id=company_a.id, user_id=user_a)
        service.create(name="B1", description=None, company_id=company_b.id, user_id=user_b)

        page = service.list_for_user(user_id=user_a)

        assert page.total == 1
        assert page.items[0].name == "A1"

    def test_orders_by_most_recently_updated(self, db_session: Session) -> None:
        user_id = uuid.uuid4()
        company = _company(db_session)
        _opportunity_for(db_session, company, user_id)

        service = PrototypeService(db_session)
        first = service.create(name="Primeiro", description=None, company_id=company.id, user_id=user_id)
        second = service.create(name="Segundo", description=None, company_id=company.id, user_id=user_id)
        service.update(second, name="Segundo (editado)")

        page = service.list_for_user(user_id=user_id)

        assert page.total == 2
        assert page.items[0].id == second.id
        assert page.items[1].id == first.id

    def test_pagination(self, db_session: Session) -> None:
        user_id = uuid.uuid4()
        company = _company(db_session)
        _opportunity_for(db_session, company, user_id)

        service = PrototypeService(db_session)
        for i in range(5):
            service.create(name=f"Proto {i}", description=None, company_id=company.id, user_id=user_id)

        page = service.list_for_user(user_id=user_id, limit=2, offset=2)

        assert page.total == 5
        assert len(page.items) == 2


class TestUpdate:
    def _prototype(self, db_session: Session, *, name: str = "Old") -> Prototype:
        user_id = uuid.uuid4()
        company = _company(db_session)
        _opportunity_for(db_session, company, user_id)
        return PrototypeService(db_session).create(name=name, description=None, company_id=company.id, user_id=user_id)

    def test_update_name_and_description(self, db_session: Session) -> None:
        prototype = self._prototype(db_session)

        updated = PrototypeService(db_session).update(prototype, name="New", description="Nova descrição")

        assert updated.name == "New"
        assert updated.description == "Nova descrição"

    def test_update_with_valid_components_persists_tree(self, db_session: Session) -> None:
        prototype = self._prototype(db_session, name="Com componentes")

        tree = [
            {"id": "c1", "type": "container", "parent_id": None, "order": 0, "props": {}, "styles": {}},
            {"id": "c2", "type": "text", "parent_id": "c1", "order": 0, "props": {"content": "Olá"}, "styles": {}},
        ]
        updated = PrototypeService(db_session).update(prototype, components=tree)

        assert len(updated.components) == 2
        reloaded = db_session.get(Prototype, prototype.id)
        assert len(reloaded.components) == 2
        assert reloaded.components[1]["props"]["content"] == "Olá"

    def test_update_with_invalid_components_raises_and_does_not_persist(self, db_session: Session) -> None:
        prototype = self._prototype(db_session, name="Vai falhar")

        bad_tree = [{"id": "c1", "type": "not-a-real-type", "parent_id": None, "order": 0}]
        with pytest.raises(Exception):
            PrototypeService(db_session).update(prototype, components=bad_tree)

        reloaded = db_session.get(Prototype, prototype.id)
        assert reloaded.components == []

    def test_partial_update_does_not_touch_other_fields(self, db_session: Session) -> None:
        user_id = uuid.uuid4()
        company = _company(db_session)
        _opportunity_for(db_session, company, user_id)
        prototype = PrototypeService(db_session).create(
            name="Original", description="Descrição original", company_id=company.id, user_id=user_id
        )

        PrototypeService(db_session).update(prototype, name="Só o nome mudou")

        reloaded = db_session.get(Prototype, prototype.id)
        assert reloaded.name == "Só o nome mudou"
        assert reloaded.description == "Descrição original"


class TestDelete:
    def test_delete_removes_the_prototype(self, db_session: Session) -> None:
        user_id = uuid.uuid4()
        company = _company(db_session)
        _opportunity_for(db_session, company, user_id)
        prototype = PrototypeService(db_session).create(
            name="Para excluir", description=None, company_id=company.id, user_id=user_id
        )

        PrototypeService(db_session).delete(prototype)

        assert db_session.get(Prototype, prototype.id) is None
