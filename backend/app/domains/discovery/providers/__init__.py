"""Registro de providers de Discovery.

Adicionar um novo provider (ex.: OpenStreetMap) é registrar uma nova
entrada aqui — nenhum outro módulo do domínio `discovery` precisa mudar,
porque `DiscoveryService` depende só de `DiscoveryProvider`
(app.domains.discovery.providers.base).

Nenhum provider de OpenStreetMap está implementado nesta fase — ver
docs/discovery.md, seção "Providers", para a justificativa.
"""
from __future__ import annotations

from app.core.config import Settings
from app.domains.discovery.providers.base import DiscoveryProvider
from app.domains.discovery.providers.errors import ProviderUnavailableError
from app.domains.discovery.providers.google_places import GooglePlacesProvider

_PROVIDER_FACTORIES = {
    "google_places": GooglePlacesProvider,
}


def get_provider(name: str, settings: Settings) -> DiscoveryProvider:
    factory = _PROVIDER_FACTORIES.get(name)
    if factory is None:
        raise ProviderUnavailableError(
            f"Provider '{name}' não é reconhecido. Providers disponíveis: "
            f"{', '.join(sorted(_PROVIDER_FACTORIES))}."
        )
    return factory(settings)


__all__ = ["DiscoveryProvider", "get_provider"]
