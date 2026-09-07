"""Contrato de provider de IA usado pela geração de Prototype (Fase 9 /
Prompt 11).

Reaproveita EXATAMENTE a mesma abstração já usada pelo Sales Brief
(Fase 4) e pelo Assisted Outreach (Fase 7) —
`app.domains.briefing.providers.base.SalesBriefProvider`/
`ProviderResponse` — em vez de duplicar uma terceira implementação
idêntica de chamada HTTP à Anthropic. A própria classe já documenta esse
precedente de reuso entre domínios; Prototype é só o terceiro. Só o
prompt (`app.domains.prototypes.generation.prompt`) e a validação
(`app.domains.prototypes.generation.validation`) são específicos deste
domínio — a chamada de rede em si não precisa de nada diferente.

`GenerationProvider` é um alias, não uma subclasse nova: um
`FakeGenerationProvider` (`fake_provider.py`) e o `AnthropicProvider`
real (`anthropic_provider.py`, também um re-export) já implementam
`SalesBriefProvider` e funcionam sem nenhuma adaptação.
"""
from __future__ import annotations

from app.domains.briefing.providers.base import ProviderResponse, SalesBriefProvider
from app.domains.briefing.providers.errors import (
    ProviderInvalidResponseError,
    ProviderRequestError,
    ProviderTemporaryError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    SalesBriefProviderError,
)

GenerationProvider = SalesBriefProvider
GenerationProviderError = SalesBriefProviderError

__all__ = [
    "GenerationProvider",
    "GenerationProviderError",
    "ProviderResponse",
    "ProviderInvalidResponseError",
    "ProviderRequestError",
    "ProviderTemporaryError",
    "ProviderTimeoutError",
    "ProviderUnavailableError",
]
