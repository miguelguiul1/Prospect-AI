"""Re-export do `AnthropicProvider` real (Fase 4) para a geração de
Prototype (Fase 9 / Prompt 11).

Não existe uma segunda implementação de chamada à API da Anthropic aqui —
`app.domains.briefing.providers.anthropic_provider.AnthropicProvider` já é
genérico (recebe `system`/`user`/`max_tokens`, não sabe nem precisa saber
se está gerando um Sales Brief, uma mensagem de Outreach ou uma árvore de
componentes de Prototype). Este módulo existe só para que
`app.domains.prototypes.generation` tenha a mesma forma de arquivo que
`app.domains.briefing.providers` (`base.py` + `anthropic_provider.py` +
um fake para teste), sem duplicar a lógica real.
"""
from __future__ import annotations

from app.domains.briefing.providers.anthropic_provider import AnthropicProvider

__all__ = ["AnthropicProvider"]
