"""Contrato que todo provider de Discovery deve seguir.

`DiscoveryService` (app.domains.discovery.service) depende exclusivamente
desta interface — nunca de uma implementação concreta como
`GooglePlacesProvider`. Isso é o que permite adicionar um novo provider
(OpenStreetMap, uma fonte comercial licenciada, ...) sem alterar o domínio
de Discovery, conforme a arquitetura da Fase 1, seção 5.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from app.domains.discovery.dto import DiscoveredCompany
from app.domains.discovery.schemas import DiscoveryQuery


@dataclass(frozen=True)
class ProviderPage:
    """Resultado de uma única chamada HTTP a um provider.

    Uma `DiscoveryQuery` paginada gera várias `ProviderPage` — uma por
    chamada real — nunca uma página "virtual" agregada, para que o custo
    (`ProviderUsageRecord`) seja rastreável por chamada.
    """

    results: list[DiscoveredCompany]
    raw_result_count: int
    operation: str
    fields_requested: list[str] = field(default_factory=list)
    next_page_token: str | None = None


class DiscoveryProvider(ABC):
    """Contrato de um provider de descoberta de empresas."""

    name: str

    @abstractmethod
    def is_configured(self) -> bool:
        """Indica se o provider tem o necessário (ex.: API key) para
        operar. Nunca lança exceção — apenas responde `False`."""
        raise NotImplementedError

    @abstractmethod
    def search(self, query: DiscoveryQuery, *, page_token: str | None = None) -> ProviderPage:
        """Executa uma única chamada de busca (uma página).

        Deve levantar uma subclasse de
        `app.domains.discovery.providers.errors.DiscoveryProviderError` em
        caso de falha — nunca deixar uma exceção de biblioteca HTTP crua
        escapar para o chamador.
        """
        raise NotImplementedError
