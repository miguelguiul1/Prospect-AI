"""Testes puros de `app.domains.prototypes.schemas.validate_component_tree`
— nenhum banco, nenhuma rede. Esta é a principal defesa de segurança do
Prototype Builder (seção 10 do Prompt 09): nenhum `type` fora do catálogo,
nenhum valor de prop que não seja um primitivo curto, nenhuma árvore
ciclica ou profunda demais.
"""
from __future__ import annotations

import pytest

from app.domains.prototypes.schemas import (
    MAX_TREE_DEPTH,
    validate_component_tree,
)


def _node(id_: str, type_: str = "text", parent_id: str | None = None, **kwargs) -> dict:
    node = {"id": id_, "type": type_, "parent_id": parent_id, "order": 0}
    node.update(kwargs)
    return node


class TestHappyPath:
    def test_empty_tree_is_valid(self) -> None:
        assert validate_component_tree([]) == []

    def test_flat_list_of_roots(self) -> None:
        result = validate_component_tree([_node("a"), _node("b", type_="button")])
        assert [n.id for n in result] == ["a", "b"]

    def test_nested_tree(self) -> None:
        tree = [
            _node("root", type_="container"),
            _node("child", type_="text", parent_id="root"),
            _node("grandchild", type_="button", parent_id="child"),
        ]
        result = validate_component_tree(tree)
        assert len(result) == 3

    def test_props_and_styles_are_preserved(self) -> None:
        tree = [_node("a", props={"content": "Olá"}, styles={"fontSize": 16})]
        result = validate_component_tree(tree)
        assert result[0].props == {"content": "Olá"}
        assert result[0].styles == {"fontSize": 16}


class TestTypeCatalog:
    def test_unknown_type_is_rejected(self) -> None:
        with pytest.raises(Exception, match="não é reconhecido"):
            validate_component_tree([_node("a", type_="script")])

    def test_every_documented_type_is_accepted(self) -> None:
        from app.domains.prototypes.schemas import COMPONENT_TYPES

        tree = [_node(f"n{i}", type_=t) for i, t in enumerate(COMPONENT_TYPES)]
        result = validate_component_tree(tree)
        assert len(result) == len(COMPONENT_TYPES)


class TestStructuralInvariants:
    def test_duplicate_ids_rejected(self) -> None:
        with pytest.raises(Exception, match="duplicados"):
            validate_component_tree([_node("a"), _node("a")])

    def test_dangling_parent_id_rejected(self) -> None:
        with pytest.raises(Exception, match="parent_id inexistente"):
            validate_component_tree([_node("a", parent_id="ghost")])

    def test_direct_cycle_rejected(self) -> None:
        with pytest.raises(Exception, match="ciclo"):
            validate_component_tree([_node("a", parent_id="b"), _node("b", parent_id="a")])

    def test_self_referencing_cycle_rejected(self) -> None:
        with pytest.raises(Exception, match="ciclo"):
            validate_component_tree([_node("a", parent_id="a")])

    def test_depth_within_limit_is_accepted(self) -> None:
        tree = [_node("n0")]
        for i in range(1, MAX_TREE_DEPTH):
            tree.append(_node(f"n{i}", parent_id=f"n{i - 1}"))
        result = validate_component_tree(tree)
        assert len(result) == MAX_TREE_DEPTH

    def test_depth_beyond_limit_is_rejected(self) -> None:
        tree = [_node("n0")]
        for i in range(1, MAX_TREE_DEPTH + 5):
            tree.append(_node(f"n{i}", parent_id=f"n{i - 1}"))
        with pytest.raises(Exception, match="[Pp]rofundidade"):
            validate_component_tree(tree)


class TestPayloadLimits:
    def test_too_many_components_rejected(self) -> None:
        from app.domains.prototypes.schemas import MAX_COMPONENTS_PER_PROTOTYPE

        tree = [_node(f"n{i}") for i in range(MAX_COMPONENTS_PER_PROTOTYPE + 1)]
        with pytest.raises(Exception, match="componentes"):
            validate_component_tree(tree)

    def test_prop_value_too_long_rejected(self) -> None:
        from app.domains.prototypes.schemas import MAX_PROP_VALUE_LENGTH

        huge = "x" * (MAX_PROP_VALUE_LENGTH + 1)
        with pytest.raises(Exception):
            validate_component_tree([_node("a", props={"content": huge})])

    def test_too_many_props_rejected(self) -> None:
        from app.domains.prototypes.schemas import MAX_PROPS_PER_COMPONENT

        many_props = {f"k{i}": "v" for i in range(MAX_PROPS_PER_COMPONENT + 1)}
        with pytest.raises(Exception):
            validate_component_tree([_node("a", props=many_props)])

    def test_prop_values_must_be_primitives(self) -> None:
        with pytest.raises(Exception):
            validate_component_tree([_node("a", props={"nested": {"not": "allowed"}})])

    def test_never_accepts_a_list_as_a_prop_value(self) -> None:
        with pytest.raises(Exception):
            validate_component_tree([_node("a", props={"items": [1, 2, 3]})])
