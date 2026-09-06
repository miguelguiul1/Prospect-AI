"""Registro de providers de IA do Sales Brief.

Adicionar um novo provider é registrar uma nova entrada aqui — nenhum outro
módulo do domínio `briefing` precisa mudar, porque `SalesBriefService`
depende só de `SalesBriefProvider` (app.domains.briefing.providers.base).
Mesmo padrão de `app.domains.discovery.providers` (Fase 1).
"""
from __future__ import annotations

from app.core.config import Settings
from app.domains.briefing.providers.anthropic_provider import AnthropicProvider
from app.domains.briefing.providers.base import SalesBriefProvider

_PROVIDER_FACTORIES = {
    "anthropic": AnthropicProvider,
}


def get_provider(settings: Settings, *, name: str | None = None) -> SalesBriefProvider:
    from app.domains.briefing.providers.errors import ProviderUnavailableError

    provider_name = name or "anthropic"
    factory = _PROVIDER_FACTORIES.get(provider_name)
    if factory is None:
        raise ProviderUnavailableError(
            f"Provider '{provider_name}' não é reconhecido. Providers disponíveis: "
            f"{', '.join(sorted(_PROVIDER_FACTORIES))}."
        )
    return factory(settings)


__all__ = ["SalesBriefProvider", "get_provider"]
