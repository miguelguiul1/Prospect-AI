"""Contrato que todo provider de IA do Sales Brief deve seguir.

`SalesBriefService` (app.domains.briefing.service) depende exclusivamente
desta interface — nunca de uma implementação concreta como
`AnthropicProvider`. Isto NÃO é um framework de agentes (nenhum CrewAI/
AutoGen/LangChain) — é uma única chamada request/response a um provider de
texto, no mesmo espírito de `DiscoveryProvider` (Fase 1).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderResponse:
    """Resposta bruta (texto) de um provider — a validação/parsing contra
    `SalesBriefContent` acontece em `app.domains.briefing.service`, não
    aqui, para que o provider não precise conhecer o schema de negócio.

    `input_tokens`/`output_tokens` são `None` a menos que o próprio provider
    os informe explicitamente na resposta — nunca estimados."""

    content: str
    model: str
    duration_ms: float
    input_tokens: int | None = None
    output_tokens: int | None = None


class SalesBriefProvider(ABC):
    """Contrato de um provider de geração de texto para o Sales Brief."""

    name: str

    @abstractmethod
    def is_configured(self) -> bool:
        """Indica se o provider tem o necessário (ex.: API key) para
        operar. Nunca lança exceção — apenas responde `False`."""
        raise NotImplementedError

    @abstractmethod
    def generate(self, *, system: str, user: str) -> ProviderResponse:
        """Executa uma única chamada de geração de texto.

        Deve levantar uma subclasse de
        `app.domains.briefing.providers.errors.SalesBriefProviderError` em
        caso de falha — nunca deixar uma exceção de biblioteca HTTP crua
        escapar para o chamador.
        """
        raise NotImplementedError
