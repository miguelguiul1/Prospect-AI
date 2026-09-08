"""Validação do artefato gerado por IA, antes de qualquer persistência
(Fase 9 / Prompt 11).

Quatro camadas, nesta ordem — a primeira falha interrompe as seguintes:

1. **Schema/catálogo** (`validate_component_tree`, já existente desde a
   Fase 6): catálogo fechado, ciclos, `parent_id` pendurado, contagem e
   profundidade máximas, IDs duplicados. NUNCA duplicada aqui — reaproveitada
   tal como está. Esta camada é inteiramente ESTRUTURAL — nunca olha para
   dentro de `props` além de tamanho/tipo de valor.
2. **Segurança de URL**: props que carregam uma URL (`src`, `href`, `url`,
   `link` — os únicos nomes usados pelo catálogo hoje, mais os dois
   últimos por precaução, já que `props` não é validado por chave no
   schema) só aceitam `http://`/`https://`/caminho relativo/vazio — nunca
   `javascript:`, `data:`, `file:`, `vbscript:`. A IA poderia gerar isso
   mesmo sem ter sido pedido (não é um caso hipotético: é exatamente o
   tipo de coisa que schemas de saída de LLM precisam checar sempre).
3. **Props obrigatórias por tipo** (`MissingRequiredPropError`) — achado
   REAL da primeira chamada real à Anthropic API deste projeto: o modelo
   devolveu uma árvore estruturalmente válida (passou a camada 1 inteira)
   mas usou `props.text` em vez de `props.content` para `heading`/
   `button` — a interface real só lê `content`, então o texto gerado
   teria sido silenciosamente descartado (substituído pelo placeholder
   padrão do Builder, nunca um espaço em branco de verdade). A camada 1
   NUNCA pegaria isso — ela valida ESTRUTURA (catálogo/ciclos/tipos de
   valor), não SEMÂNTICA (quais props um tipo específico precisa ter
   preenchidas). Esta camada fecha exatamente essa lacuna, mas só para o
   caso concreto já observado (texto ausente em componentes que exibem
   texto) — não é um schema completo por tipo de componente (ver "Nota de
   escopo" abaixo).
4. **Grounding heurístico** (não uma garantia — ver docstring de
   `find_grounding_warnings`): sinaliza texto gerado que parece conter um
   fato numérico específico (telefone, CNPJ, preço) sem bater com nenhum
   valor conhecido do `PrototypeContext`. Nunca bloqueia a geração —
   produz avisos persistidos junto do `GenerationRun`, para revisão
   humana.

**Nota de escopo (Prompt 11)**: a camada 3 resolve o bug concreto já
observado (texto ausente), não implementa um schema Pydantic completo por
tipo de componente (ex.: `image` exigindo `alt`, `input` exigindo
`inputType` válido, etc.) — isso é uma extensão maior, deliberadamente
deixada como decisão em aberto para o relatório final desta fase (ver
`docs/prototype-generation.md`), não porque seja overengineering em si,
mas porque o valor marginal de validar CADA prop de CADA tipo ainda não
foi provado por um segundo achado real — a primeira fez foi sobre texto
ausente, que é o único caso concreto corrigido aqui.
"""
from __future__ import annotations

import re

from app.domains.prototypes.context import PrototypeContext
from app.domains.prototypes.schemas import PrototypeComponentInput, validate_component_tree

_SAFE_URL_PREFIXES = ("http://", "https://", "/")
_URL_PROP_KEYS = ("src", "href", "url", "link")

# Tipos cujo propósito inteiro é exibir texto — sem `props.content`
# preenchido, o componente renderiza o placeholder padrão do Builder
# ("Título", "Clique aqui", etc.), nunca o texto que a IA de fato gerou.
_CONTENT_REQUIRED_TYPES = frozenset({"text", "heading", "button"})


class UnsafeGeneratedContentError(ValueError):
    """Uma prop de URL gerada usa um esquema perigoso (`javascript:`,
    `data:`, `file:`, `vbscript:`, ou qualquer coisa que não seja
    http(s)/caminho relativo/vazio)."""


class MissingRequiredPropError(ValueError):
    """Um componente de tipo `text`/`heading`/`button` não tem
    `props.content` preenchido (ausente, vazio, ou com o nome de prop
    errado, ex.: `props.text`) — passaria na validação de catálogo/
    estrutura mas renderizaria com o placeholder padrão do Builder na UI
    real, descartando silenciosamente o texto que a IA gerou."""


def validate_generated_tree(raw_components: list[dict]) -> list[PrototypeComponentInput]:
    """Levanta `ValueError` (catálogo/estrutura, camada 1),
    `UnsafeGeneratedContentError` (camada 2) ou `MissingRequiredPropError`
    (camada 3) — nunca persiste uma árvore que falhou em qualquer uma das
    três. Não roda a camada 4 (`find_grounding_warnings`) — essa precisa
    do `PrototypeContext` e é chamada separadamente pelo
    `PrototypeGenerationService`, porque avisos de grounding nunca
    bloqueiam a persistência."""
    parsed = validate_component_tree(raw_components)
    _check_url_safety(parsed)
    _check_required_content_prop(parsed)
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


def _check_required_content_prop(nodes: list[PrototypeComponentInput]) -> None:
    for node in nodes:
        if node.type not in _CONTENT_REQUIRED_TYPES:
            continue
        content = node.props.get("content")
        if not isinstance(content, str) or not content.strip():
            raise MissingRequiredPropError(
                f"componente '{node.id}' ({node.type}) precisa de props.content preenchido "
                "(string não vazia) — sem isso, a interface real mostra um placeholder genérico "
                "em vez do texto gerado."
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


__all__ = [
    "validate_generated_tree",
    "find_grounding_warnings",
    "UnsafeGeneratedContentError",
    "MissingRequiredPropError",
]
