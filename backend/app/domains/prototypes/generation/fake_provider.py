"""Provider de IA fake para testar a geração de Prototype (Fase 9 /
Prompt 11) — NUNCA usado por nenhum caminho de requisição real.

Vive neste módulo (não só dentro de um arquivo de teste, diferente do
padrão de `tests/outreach/test_service.py::_FakeProvider`) porque várias
suítes de teste diferentes precisam dele — `tests/prototypes/
test_generation_service.py`, `test_api.py` (rota `/generate`), e possíveis
testes futuros de `jobs.py` — e duplicar a mesma classe em cada arquivo
divergiria com o tempo. Nenhum código de produção importa este módulo.
"""
from __future__ import annotations

import json

from app.domains.prototypes.generation.base import GenerationProvider, ProviderResponse

DEFAULT_COMPONENT_TREE = [
    {
        "id": "root",
        "type": "container",
        "parent_id": None,
        "order": 0,
        "props": {},
        "styles": {},
    },
    {
        "id": "hero-heading",
        "type": "heading",
        "parent_id": "root",
        "order": 0,
        "props": {"content": "Bem-vindo"},
        "styles": {},
    },
    {
        "id": "hero-text",
        "type": "text",
        "parent_id": "root",
        "order": 1,
        "props": {"content": "Fale conosco para saber mais sobre nossos produtos."},
        "styles": {},
    },
    {
        "id": "hero-image",
        "type": "image",
        "parent_id": "root",
        "order": 2,
        "props": {"placeholder": True},
        "styles": {},
    },
    {
        "id": "cta-button",
        "type": "button",
        "parent_id": "root",
        "order": 3,
        "props": {"content": "Entre em contato"},
        "styles": {},
    },
]


class FakeGenerationProvider(GenerationProvider):
    """Nunca chama rede — devolve `response_text` (por padrão, uma árvore
    de componentes válida) ou levanta `error`, exatamente como
    `AnthropicProvider` faria em cada caso, sem custo e sem
    não-determinismo."""

    name = "fake"

    def __init__(
        self,
        *,
        component_tree: list[dict] | None = None,
        response_text: str | None = None,
        error: Exception | None = None,
        input_tokens: int | None = 120,
        output_tokens: int | None = 340,
    ) -> None:
        if response_text is not None:
            self._response_text = response_text
        else:
            self._response_text = json.dumps({"components": component_tree or DEFAULT_COMPONENT_TREE})
        self._error = error
        self._input_tokens = input_tokens
        self._output_tokens = output_tokens
        self.last_call: dict | None = None

    def is_configured(self) -> bool:
        return True

    def generate(self, *, system: str, user: str, max_tokens: int | None = None) -> ProviderResponse:
        self.last_call = {"system": system, "user": user, "max_tokens": max_tokens}
        if self._error is not None:
            raise self._error
        return ProviderResponse(
            content=self._response_text,
            model="fake-model-1",
            duration_ms=8.0,
            input_tokens=self._input_tokens,
            output_tokens=self._output_tokens,
        )


__all__ = ["FakeGenerationProvider", "DEFAULT_COMPONENT_TREE"]
