"""Hierarquia de erro comum a qualquer provider de IA do Sales Brief.

Espelha `app.domains.discovery.providers.errors` (Fase 1): `retryable`
decide se vale tentar de novo dentro do mesmo request — aqui o Sales Brief
NUNCA tenta novamente automaticamente (uma chamada de IA já é cara e lenta o
suficiente; um erro vira um `SalesBrief.status=FAILED` imediato, nunca um
retry silencioso que poderia mascarar instabilidade do provider).
"""
from __future__ import annotations


class SalesBriefProviderError(Exception):
    """Erro base de qualquer provider de Sales Brief."""

    retryable: bool = False


class ProviderUnavailableError(SalesBriefProviderError):
    """Provider não configurado (ex.: sem API key) ou desconhecido.

    Este é o caminho de degradação graciosa exigido pela Fase 4: o
    Opportunity Score continua funcionando normalmente mesmo quando isto
    acontece — só o Sales Brief fica indisponível, de forma explícita e
    nunca mascarada como sucesso.
    """


class ProviderTimeoutError(SalesBriefProviderError):
    """A chamada ao provider excedeu o timeout configurado."""


class ProviderTemporaryError(SalesBriefProviderError):
    """Erro transitório do lado do provider: HTTP 429 (rate limit) ou 5xx.

    Distinto de `ProviderTimeoutError` (não houve timeout — o provider
    respondeu, só que com um erro temporário) e de `ProviderRequestError`
    (não é um problema da nossa requisição/credencial). Como o Sales Brief
    nunca tenta novamente automaticamente (ver docstring do módulo), esta
    classe existe só para que o `SalesBrief.error_code` persistido seja
    honesto sobre a causa real, não para acionar retry."""


class ProviderRequestError(SalesBriefProviderError):
    """Erro do lado da requisição/credencial (4xx) ou falha de transporte
    irrecuperável — nunca deve ser interpretado como "sem oportunidade"."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class ProviderInvalidResponseError(SalesBriefProviderError):
    """O provider respondeu, mas o conteúdo não é JSON válido ou não valida
    contra `app.domains.briefing.schemas.SalesBriefContent`. Nunca aceitamos
    uma resposta fora do formato esperado só para "aproveitar" a chamada
    feita — melhor um `FAILED` explícito do que um brief mal-formado."""
