"""Testes de `app.domains.prototypes.versioning` (Fase 9 / Prompt 12) —
`create_version`/`PrototypeVersionService`, independente do Generation
Engine (que já tem sua própria suíte de ponta a ponta)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.domains.prototypes.models import Prototype
from app.domains.prototypes.versioning import PrototypeVersionService, create_version


def _prototype(db: Session) -> Prototype:
    prototype = Prototype(name="Site de Teste", company_id=None, components=[], settings={})
    db.add(prototype)
    db.flush()
    return prototype


_TREE_V1 = [{"id": "a", "type": "text", "parent_id": None, "order": 0, "props": {"content": "v1"}, "styles": {}}]
_TREE_V2 = [{"id": "a", "type": "text", "parent_id": None, "order": 0, "props": {"content": "v2"}, "styles": {}}]


class TestCreateVersion:
    def test_first_version_is_number_one(self, db_session: Session) -> None:
        prototype = _prototype(db_session)

        version = create_version(db_session, prototype, components=_TREE_V1)

        assert version.version_number == 1
        assert prototype.components == _TREE_V1

    def test_second_version_increments_and_updates_prototype_components(self, db_session: Session) -> None:
        prototype = _prototype(db_session)
        create_version(db_session, prototype, components=_TREE_V1)

        second = create_version(db_session, prototype, components=_TREE_V2)

        assert second.version_number == 2
        assert prototype.components == _TREE_V2  # sempre reflete a mais recente

    def test_restored_from_version_number_is_recorded_when_provided(self, db_session: Session) -> None:
        prototype = _prototype(db_session)
        create_version(db_session, prototype, components=_TREE_V1)

        version = create_version(db_session, prototype, components=_TREE_V1, restored_from_version_number=1)

        assert version.restored_from_version_number == 1
        assert version.generation_run_id is None


class TestPrototypeVersionService:
    def test_list_for_prototype_returns_newest_first(self, db_session: Session) -> None:
        prototype = _prototype(db_session)
        create_version(db_session, prototype, components=_TREE_V1)
        create_version(db_session, prototype, components=_TREE_V2)

        versions = PrototypeVersionService(db_session).list_for_prototype(prototype.id)

        assert [v.version_number for v in versions] == [2, 1]

    def test_get_returns_none_for_a_version_of_a_different_prototype(self, db_session: Session) -> None:
        prototype_a = _prototype(db_session)
        prototype_b = _prototype(db_session)
        version = create_version(db_session, prototype_a, components=_TREE_V1)

        assert PrototypeVersionService(db_session).get(prototype_b.id, version.id) is None
        assert PrototypeVersionService(db_session).get(prototype_a.id, version.id) is version

    def test_restore_creates_a_new_version_with_the_old_components_never_deletes_history(
        self, db_session: Session
    ) -> None:
        prototype = _prototype(db_session)
        v1 = create_version(db_session, prototype, components=_TREE_V1)
        create_version(db_session, prototype, components=_TREE_V2)

        service = PrototypeVersionService(db_session)
        restored = service.restore(prototype, v1)

        assert restored.version_number == 3  # nunca sobrescreve, sempre uma linha nova
        assert restored.components == _TREE_V1
        assert restored.restored_from_version_number == 1
        assert prototype.components == _TREE_V1  # "atual" agora é a restaurada
        assert len(service.list_for_prototype(prototype.id)) == 3  # histórico completo preservado
