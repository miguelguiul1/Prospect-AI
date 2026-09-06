"""Catálogo de componentes e validação da árvore do Prototype Builder.

Duas regras de segurança concretas vivem aqui (seção "Segurança" da Fase 6):

1. **Nenhum `type` fora do catálogo é aceito.** `COMPONENT_TYPES` é a única
   fonte de verdade — o mesmo catálogo é espelhado no frontend
   (`frontend/src/lib/prototype/component-registry.ts`), mas o backend
   nunca confia no frontend para essa checagem.
2. **`props`/`styles` só aceitam valores primitivos (str/int/float/bool),
   com tamanho limitado.** Isso é o que torna impossível usar um protótipo
   para armazenar HTML/JavaScript arbitrário: como o frontend nunca
   interpreta esses valores como HTML (sempre texto/atributos React
   comuns — ver `docs/prototype-builder.md`), e o backend nunca aceita um
   valor que não seja um primitivo curto, não há superfície para injetar
   nada executável.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

# Catálogo inicial de componentes (seção 4 do Prompt 09) — pequeno de
# propósito. Adicionar um tipo novo é só acrescentar uma entrada aqui (e no
# registry do frontend), nunca exige mudar a estrutura de `Prototype`.
COMPONENT_TYPES: frozenset[str] = frozenset(
    {
        # layout
        "container", "section", "row", "column",
        # conteúdo
        "text", "heading", "button", "image",
        # formulário
        "input", "textarea",
        # interface
        "card", "divider",
    }
)

# Limites internos (nossos, não do usuário) — impedem que um payload
# gigante ou profundamente aninhado vire um vetor de negação de serviço.
MAX_COMPONENTS_PER_PROTOTYPE = 300
MAX_TREE_DEPTH = 12
MAX_PROP_VALUE_LENGTH = 4000
MAX_PROPS_PER_COMPONENT = 40

PrimitiveValue = str | int | float | bool | None


class PrototypeComponentInput(BaseModel):
    """Um nó da árvore, no formato aceito pela API (lista plana)."""

    id: str = Field(..., min_length=1, max_length=64)
    type: str
    parent_id: str | None = Field(default=None, max_length=64)
    order: int = Field(default=0, ge=0, le=MAX_COMPONENTS_PER_PROTOTYPE)
    props: dict[str, PrimitiveValue] = Field(default_factory=dict)
    styles: dict[str, PrimitiveValue] = Field(default_factory=dict)

    @field_validator("type")
    @classmethod
    def _type_in_catalog(cls, value: str) -> str:
        if value not in COMPONENT_TYPES:
            raise ValueError(
                f"tipo de componente '{value}' não é reconhecido. "
                f"Tipos disponíveis: {', '.join(sorted(COMPONENT_TYPES))}."
            )
        return value

    @field_validator("props", "styles")
    @classmethod
    def _values_are_short_primitives(cls, value: dict[str, PrimitiveValue]) -> dict[str, PrimitiveValue]:
        if len(value) > MAX_PROPS_PER_COMPONENT:
            raise ValueError(f"no máximo {MAX_PROPS_PER_COMPONENT} propriedades por componente.")
        for key, item in value.items():
            if isinstance(item, str) and len(item) > MAX_PROP_VALUE_LENGTH:
                raise ValueError(f"o valor de '{key}' excede {MAX_PROP_VALUE_LENGTH} caracteres.")
        return value


def validate_component_tree(components: list[dict]) -> list[PrototypeComponentInput]:
    """Valida a árvore inteira: cada nó individualmente (via
    `PrototypeComponentInput`), mais as invariantes estruturais que um
    único nó não consegue checar sozinho — quantidade total, IDs únicos,
    `parent_id` apontando para um nó que existe, e profundidade máxima
    (contra ciclos e contra aninhamento abusivo).

    Levanta `ValueError` com uma mensagem clara em qualquer violação —
    nunca persiste uma árvore parcialmente inválida.
    """
    if len(components) > MAX_COMPONENTS_PER_PROTOTYPE:
        raise ValueError(f"um protótipo não pode ter mais que {MAX_COMPONENTS_PER_PROTOTYPE} componentes.")

    parsed = [PrototypeComponentInput.model_validate(item) for item in components]

    ids = [node.id for node in parsed]
    if len(set(ids)) != len(ids):
        raise ValueError("IDs de componente duplicados na árvore.")

    id_set = set(ids)
    by_id = {node.id: node for node in parsed}
    for node in parsed:
        if node.parent_id is not None and node.parent_id not in id_set:
            raise ValueError(f"componente '{node.id}' referencia um parent_id inexistente.")

    def depth_of(node_id: str, seen: frozenset[str]) -> int:
        node = by_id[node_id]
        if node.parent_id is None:
            return 1
        if node.parent_id in seen:
            raise ValueError(f"ciclo detectado envolvendo o componente '{node_id}'.")
        return 1 + depth_of(node.parent_id, seen | {node_id})

    for node in parsed:
        if depth_of(node.id, frozenset()) > MAX_TREE_DEPTH:
            raise ValueError(f"profundidade máxima de {MAX_TREE_DEPTH} excedida em '{node.id}'.")

    return parsed


class PrototypeCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)


class PrototypeUpdateRequest(BaseModel):
    """Todos os campos são opcionais — só os enviados são atualizados.

    `components`, quando enviado, substitui a árvore inteira (o Builder
    sempre manda o estado completo ao salvar — mais simples e determinístico
    que um patch incremental, e evita divergência entre o que o editor
    mostra e o que fica persistido)."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    components: list[dict] | None = None
    settings: dict | None = None


class ComponentTypeInfo(BaseModel):
    type: str
    category: Literal["layout", "content", "form", "interface"]


# Espelha a categorização da seção 4 do Prompt 09 — só para a API de
# catálogo (`GET /api/prototypes/meta/component-types`); a fonte de
# verdade de validação continua sendo `COMPONENT_TYPES` acima.
COMPONENT_CATEGORIES: dict[str, str] = {
    "container": "layout", "section": "layout", "row": "layout", "column": "layout",
    "text": "content", "heading": "content", "button": "content", "image": "content",
    "input": "form", "textarea": "form",
    "card": "interface", "divider": "interface",
}
