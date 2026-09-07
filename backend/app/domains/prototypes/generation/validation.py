"""Validação do artefato gerado por IA, antes de qualquer persistência
(Fase 9 / Prompt 11).

Três camadas, nesta ordem — a primeira falha interrompe as seguintes:

1. **Schema/catálogo** (`validate_component_tree`, já existente desde a
   Fase 6): catálogo fechado, ciclos, `parent_id` pendurado, contagem e
   profundidade máximas, IDs duplicados. NUNCA duplicada aqui — reaproveitada
   tal como está.
2. **Segurança de URL**: props que carregam uma URL (`src`, `href`, `url`,
   `link` — os únicos nomes usados pelo catálogo hoje, mais os dois
   últimos por precaução, já que `props` não é validado por chave no
   schema) só aceitam `http://`/`https://`/caminho relativo/vazio — nunca
   `javascript:`, `data:`, `file:`, `vbscript:`. A IA poderia gerar isso
   mesmo sem ter sido pedido (não é um caso hipotético: é exatamente o
   tipo de coisa que schemas de saída de LLM precisam checar sempre).
3. **Grounding heurístico** (não uma garantia — ver docstring de
   `find_grounding_warnings`): sinaliza texto gerado que parece conter um
   fato numérico específico (telefone, CNPJ, preço) sem bater com nenhum
   valor conhecido do `PrototypeContext`. Nunca bloqueia a geração —
   produz avisos persistidos junto do `GenerationRun`, para revisão
   humana.
"""
from __future__ import annotations

import re

from app.domains.prototypes.context import PrototypeContext
from app.domains.prototypes.schemas import PrototypeComponentInput, validate_component_tree

_SAFE_URL_PREFIXES = ("http://", "https://", "/")
_URL_PROP_KEYS = ("src", "href", "url", "link")


class UnsafeGeneratedContentError(ValueError):
    """Uma prop de URL gerada usa um esquema perigoso (`javascript:`,
    `data:`, `file:`, `vbscript:`, ou qualquer coisa que não seja
    http(s)/caminho relativo/vazio)."""


def validate_generated_tree(raw_components: list[dict]) -> list[PrototypeComponentInput]:
    """Levanta `ValueError` (catálogo/estrutura, da camada 1) ou
    `UnsafeGeneratedContentError` (camada 2) — nunca persiste uma árvore
    que falhou em qualquer uma das duas. Não roda a camada 3
    (`find_grounding_warnings`) — essa precisa do `PrototypeContext` e é
    chamada separadamente pelo `PrototypeGenerationService`, porque
    avisos de grounding nunca bloqueiam a persistência."""
    parsed = validate_component_tree(raw_components)
    _check_url_safety(parsed)
    return parsed


def _check_url_safety(nodes: list[PrototypeComponentInput]) -> None:
    for node in nodes:
        for key in _URL_PROP_KEYS:
            value = node.props.get(key)
            if value is None or not isinstance(value, str) or value == "":
                continue
            if not value.startswith(_SAFE_URL_PREFIXES):
                raise UnsafeGeneratedContentError(
                    f"componente '{node.id}' ({node.type}) tem '{key}' com esquema não permitido: "
                    f"'{value[:60]}'. Só http://, https:// ou caminho relativo são aceitos."
                )


# Padrões propositalmente simples (regex/keyword, não NLP) — heurística de
# primeira linha de defesa, nunca uma garantia de que nada foi inventado.
_PHONE_PATTERN = re.compile(r"(?:\+?\d{2}\s?)?\(?\d{2}\)?[\s.-]?\d{4,5}[\s.-]?\d{4}")
_CNPJ_PATTERN = re.compile(r"\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}")
_PRICE_PATTERN = re.compile(r"R\$\s?\d+[.,]?\d*")


def find_grounding_warnings(nodes: list[PrototypeComponentInput], context: PrototypeContext) -> list[str]:
    """Heurística por regex/keyword — nunca uma garantia (ver docstring do
    módulo). Extrai todo texto de `props.content`/`props.label`/
    `props.placeholder`, procura por algo que PARECE um telefone/CNPJ/
    preço, e sinaliza se esse trecho não aparece em nenhum valor
    FACT/SIGNAL conhecido do contexto — nunca bloqueia, só relata."""
    known_values = {
        str(field.value).strip()
        for field in context.all_fields().values()
        if field.confidence.value in ("fact", "signal") and field.value is not None
    }
    known_text = " ".join(known_values)

    warnings: list[str] = []
    for node in nodes:
        for prop_key in ("content", "label", "placeholder"):
            text = node.props.get(prop_key)
            if not isinstance(text, str):
                continue
            for pattern, kind in (
                (_PHONE_PATTERN, "telefone"),
                (_CNPJ_PATTERN, "CNPJ"),
                (_PRICE_PATTERN, "preço"),
            ):
                for match in pattern.finditer(text):
                    matched_text = match.group(0)
                    if matched_text not in known_text:
                        warnings.append(
                            f"componente '{node.id}' ({node.type}.{prop_key}) contém algo que parece "
                            f"{kind} ('{matched_text}') sem correspondência em nenhum campo FACT/SIGNAL "
                            "do contexto — revisar antes de usar."
                        )
    return warnings


__all__ = ["validate_generated_tree", "find_grounding_warnings", "UnsafeGeneratedContentError"]
