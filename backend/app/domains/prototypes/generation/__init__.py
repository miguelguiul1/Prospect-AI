"""Geração de Prototype por IA (Fase 9 / Prompt 11) — uma única chamada
request/response a um provider de texto, nunca multi-agente (confirmado
pela auditoria: "não usar multi-agente nesta fase"). Ver `service.py`
para o fluxo completo: `PrototypeContext` -> prompt -> provider ->
validação -> persistência.
"""
from __future__ import annotations

from app.core.config import Settings
from app.domains.prototypes.generation.base import GenerationProvider


def get_generation_provider(settings: Settings) -> GenerationProvider:
    """Reaproveita o registro de providers do Sales Brief
    (`app.domains.briefing.providers.get_provider`) — não existe um
    segundo registro/factory aqui, porque o único provider real
    (`AnthropicProvider`) já é o mesmo objeto de configuração
    (`anthropic_api_key`/`anthropic_model`)."""
    from app.domains.briefing.providers import get_provider

    return get_provider(settings)


__all__ = ["get_generation_provider", "GenerationProvider"]
