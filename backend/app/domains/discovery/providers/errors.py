"""Hierarquia de erro comum a qualquer provider de Discovery.

`retryable` decide se o loop de chamada (`app.domains.discovery.http.
call_with_retry`) tenta novamente — nunca implementamos retry infinito, e
nunca tentamos retry para um erro que representa um problema permanente
(credencial inválida, parâmetro inválido).
"""
from __future__ import annotations


class DiscoveryProviderError(Exception):
    """Erro base de qualquer provider de Discovery."""

    retryable: bool = False


class ProviderUnavailableError(DiscoveryProviderError):
    """Provider não configurado (ex.: sem API key) ou desconhecido."""

    retryable = False


class ProviderRequestError(DiscoveryProviderError):
    """Erro permanente do lado da requisição: parâmetro inválido (400) ou
    credencial rejeitada (401/403). Nunca deve ser repetido sem alterar a
    requisição."""

    retryable = False

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class ProviderRateLimitedError(DiscoveryProviderError):
    """HTTP 429 — cota do provider excedida."""

    retryable = True

    def __init__(self, message: str = "Provider retornou 429 (rate limited)") -> None:
        super().__init__(message)


class ProviderTemporaryError(DiscoveryProviderError):
    """Erro transitório: timeout, falha de conexão ou 5xx. Elegível a
    retry limitado com backoff."""

    retryable = True

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
