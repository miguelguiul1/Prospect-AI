"""Validação contra a API REAL da Anthropic — nunca simulado.

Mesma filosofia de `test_real_postgres.py`/`test_real_redis.py`: pulado com
motivo explícito quando `ANTHROPIC_API_KEY` não está configurada (o caso de
toda sessão deste projeto até aqui — nenhuma chave de API foi fornecida em
nenhuma fase). NUNCA loga a chave nem qualquer parte dela — só a presença
(configurada/ausente) é observável em qualquer saída deste arquivo.

Se uma chave real for configurada (localmente ou como GitHub Secret em CI),
este arquivo faz uma ÚNICA chamada real e mínima (poucas dezenas de tokens)
— nunca geração em lote, nunca um teste de carga contra a API paga.
"""
from __future__ import annotations

import os

import pytest

from app.core.config import Settings
from app.domains.briefing.providers.anthropic_provider import AnthropicProvider
from app.domains.briefing.providers.errors import SalesBriefProviderError

_HAS_REAL_KEY = bool(os.environ.get("ANTHROPIC_API_KEY"))

pytestmark = pytest.mark.skipif(
    not _HAS_REAL_KEY,
    reason=(
        "ANTHROPIC_API_KEY ausente — nenhuma chamada real à Anthropic é possível. "
        "Esperado em toda sessão deste projeto até a Fase 8 (nenhuma chave foi "
        "fornecida em nenhuma fase). Ver docs/production-readiness.md."
    ),
)


@pytest.fixture()
def real_provider() -> AnthropicProvider:
    settings = Settings()  # lê ANTHROPIC_API_KEY do ambiente real, nunca hardcoded
    return AnthropicProvider(settings)


class TestRealAnthropicCall:
    def test_is_configured_reports_true_with_a_real_key_present(self, real_provider: AnthropicProvider) -> None:
        assert real_provider.is_configured() is True

    def test_a_minimal_real_generation_call_succeeds(self, real_provider: AnthropicProvider) -> None:
        """Chamada real única, mínima — prova conectividade/autenticação
        de ponta a ponta contra a API real, algo que nenhuma sessão deste
        projeto conseguiu validar até a Fase 8."""
        try:
            response = real_provider.generate(
                system="Responda apenas com a palavra 'ok', em minúsculas, sem pontuação.",
                user="teste de conectividade",
                max_tokens=10,
            )
        except SalesBriefProviderError as exc:
            pytest.fail(f"Chamada real à Anthropic falhou: {exc.__class__.__name__}: {exc}")

        assert response.content.strip()
        assert response.model
        assert response.duration_ms > 0
        # input_tokens/output_tokens só são preenchidos se a própria API os
        # retornar (nunca estimados) — aqui, com uma chave real, devem vir.
        assert response.input_tokens is not None
        assert response.output_tokens is not None
