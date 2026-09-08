"""Testes de `app.core.ai_text.strip_markdown_code_fence` (Prompt 11 —
achado real da primeira chamada real à Anthropic API deste projeto: o
modelo real ocasionalmente envolve JSON em um bloco de código Markdown
apesar da instrução explícita para não fazer isso)."""
from __future__ import annotations

from app.core.ai_text import strip_markdown_code_fence


class TestStripMarkdownCodeFence:
    def test_plain_json_is_returned_unchanged(self) -> None:
        text = '{"a": 1}'
        assert strip_markdown_code_fence(text) == text

    def test_json_fence_with_language_tag_is_stripped(self) -> None:
        text = '```json\n{"a": 1}\n```'
        assert strip_markdown_code_fence(text) == '{"a": 1}'

    def test_fence_without_language_tag_is_stripped(self) -> None:
        text = '```\n{"a": 1}\n```'
        assert strip_markdown_code_fence(text) == '{"a": 1}'

    def test_surrounding_whitespace_is_trimmed_either_way(self) -> None:
        assert strip_markdown_code_fence('  {"a": 1}  \n') == '{"a": 1}'
        assert strip_markdown_code_fence('  ```json\n{"a": 1}\n```  ') == '{"a": 1}'

    def test_multiline_json_inside_the_fence_is_preserved(self) -> None:
        text = '```json\n{\n  "a": 1,\n  "b": 2\n}\n```'
        assert strip_markdown_code_fence(text) == '{\n  "a": 1,\n  "b": 2\n}'

    def test_prose_around_a_fence_is_never_stripped(self) -> None:
        """Deliberado: um bloco de código em MEIO a texto livre não é
        extraído — isso mascararia uma resposta que genuinamente não
        seguiu o formato pedido. Essa entrada deve continuar falhando a
        validação JSON normalmente, não ser silenciosamente aceita."""
        text = 'Aqui está o JSON:\n```json\n{"a": 1}\n```\nEspero que ajude!'
        assert strip_markdown_code_fence(text) == text
