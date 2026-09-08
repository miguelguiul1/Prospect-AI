"""Testes de `app.domains.prototypes.generation.diffing` (Fase 9 /
Prompt 12) — a metade "medir" do incentivo a mudança mínima no
refinamento (a metade "incentivar" é o prompt, testada em
`test_generation_prompt.py`)."""
from __future__ import annotations

from app.domains.prototypes.generation.diffing import summarize_component_diff


def _node(node_id: str, *, content: str = "x") -> dict:
    return {"id": node_id, "type": "text", "parent_id": None, "order": 0, "props": {"content": content}, "styles": {}}


class TestSummarizeComponentDiff:
    def test_identical_trees_have_zero_changed_ratio(self) -> None:
        tree = [_node("a"), _node("b"), _node("c")]
        result = summarize_component_diff(tree, tree)

        assert result["changed_ratio"] == 0.0
        assert result["added_ids"] == []
        assert result["removed_ids"] == []
        assert result["changed_ids"] == []
        assert result["unchanged_count"] == 3

    def test_a_single_changed_component_out_of_five_has_a_low_ratio(self) -> None:
        """O caso descrito na seção 3 do Prompt 12: pedir para mudar a cor
        do botão não deveria reescrever o hero inteiro — um refinamento
        bem comportado altera 1 de 5 componentes."""
        before = [_node("hero"), _node("subtitle"), _node("cta"), _node("footer"), _node("logo")]
        after = [_node("hero"), _node("subtitle"), _node("cta", content="novo texto"), _node("footer"), _node("logo")]

        result = summarize_component_diff(before, after)

        assert result["changed_ids"] == ["cta"]
        assert result["added_ids"] == []
        assert result["removed_ids"] == []
        assert result["unchanged_count"] == 4
        assert result["changed_ratio"] == 0.2

    def test_a_rewritten_tree_has_a_high_ratio(self) -> None:
        """O caso oposto — se o modelo ignorar a instrução de mudança
        mínima e reescrever tudo, o diff torna isso visível (nunca
        bloqueia, só sinaliza — ver docstring do módulo)."""
        before = [_node("a"), _node("b")]
        after = [_node("x"), _node("y"), _node("z")]

        result = summarize_component_diff(before, after)

        assert set(result["removed_ids"]) == {"a", "b"}
        assert set(result["added_ids"]) == {"x", "y", "z"}
        assert result["changed_ratio"] == 2.5  # (0 changed + 2 removed + 3 added) / 2

    def test_empty_before_tree_never_divides_by_zero(self) -> None:
        result = summarize_component_diff([], [_node("a")])
        assert result["components_before"] == 0
        assert result["changed_ratio"] == 1.0
