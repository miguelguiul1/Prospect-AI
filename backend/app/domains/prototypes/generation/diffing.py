"""Diff aproximado entre a árvore de componentes ANTES e DEPOIS de um
refinamento (Fase 9 / Prompt 12) — heurística de OBSERVABILIDADE, nunca um
gate de validação.

Mede o QUANTO mudou (quantos componentes foram adicionados/removidos/
alterados em relação ao total anterior), não SE deveria ter mudado — não
há como um sistema determinístico saber se uma reescrita ampla era ou não
o que o pedido do usuário exigia sem entender a intenção em linguagem
natural, e isso está fora do escopo desta fase. `GenerationRun.
diff_summary` guarda o resultado só para revisão humana: um refinamento
que pediu "muda a cor do botão" e voltou com `changed_ratio` alto é um
sinal de que a IA reescreveu mais do que o pedido, mas isso nunca bloqueia
a geração nem é usado para rejeitar automaticamente — mesma filosofia de
`find_grounding_warnings` (Prompt 11): sinalizar, nunca decidir sozinho.

**Limitação documentada (seção 3 do Prompt 12)**: isto é a metade
"medir" da instrução ("decida como medir/incentivar isso, mesmo que de
forma aproximada"); a metade "incentivar" vive no prompt de refinamento
(`app.domains.prototypes.generation.prompt.REFINEMENT_SYSTEM_PROMPT`),
que pede explicitamente ao modelo para preservar tudo que não tem relação
com o pedido. Nenhuma das duas metades GARANTE um diff mínimo — um modelo
pode ignorar a instrução do prompt e reescrever componentes sem relação
nenhuma com o pedido, e nada aqui impede isso, só torna visível depois.
"""
from __future__ import annotations


def summarize_component_diff(before: list[dict], after: list[dict]) -> dict:
    """Compara duas árvores planas de componentes por `id`. Um componente
    presente nos dois lados mas com qualquer campo diferente (`type`,
    `parent_id`, `order`, `props`, `styles`) conta como "alterado" —
    comparação por igualdade de dict inteiro, não por diff campo a campo
    (suficiente para medir "o tamanho da mudança", não para explicar
    exatamente o que mudou dentro de um componente)."""
    before_by_id = {node["id"]: node for node in before}
    after_by_id = {node["id"]: node for node in after}

    added_ids = sorted(set(after_by_id) - set(before_by_id))
    removed_ids = sorted(set(before_by_id) - set(after_by_id))
    common_ids = set(before_by_id) & set(after_by_id)
    changed_ids = sorted(cid for cid in common_ids if before_by_id[cid] != after_by_id[cid])

    total_before = len(before_by_id) or 1  # evita divisão por zero quando a árvore anterior era vazia
    changed_ratio = round((len(added_ids) + len(removed_ids) + len(changed_ids)) / total_before, 4)

    return {
        "components_before": len(before_by_id),
        "components_after": len(after_by_id),
        "added_ids": added_ids,
        "removed_ids": removed_ids,
        "changed_ids": changed_ids,
        "unchanged_count": len(common_ids) - len(changed_ids),
        "changed_ratio": changed_ratio,
    }


__all__ = ["summarize_component_diff"]
