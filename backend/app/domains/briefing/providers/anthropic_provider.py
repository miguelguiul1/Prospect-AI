"""Provider Anthropic (Claude) para o Sales Brief.

Implementado com `httpx` puro contra a Messages API pública da Anthropic
(`POST /v1/messages`, header `x-api-key` + `anthropic-version`) — não com o
SDK oficial `anthropic`. Decisão deliberada de dependência mínima (mesma
filosofia das Fases 0-3, que preferem `httpx`/stdlib a uma biblioteca nova
sempre que a chamada é simples o suficiente): esta é uma única chamada
POST/JSON sem streaming, sem uso de ferramentas (tools) e sem multi-turno —
o SDK inteiro traria muito mais superfície do que a Fase 4 precisa. Ver
`docs/sales-brief.md`, seção "Por que httpx, não o SDK `anthropic`".

Referência: https://docs.anthropic.com/en/api/messages
"""
from __future__ import annotations

import time
from typing import Any

import httpx

from app.core.config import Settings
from app.domains.briefing.providers.base import ProviderResponse, SalesBriefProvider
from app.domains.briefing.providers.errors import (
    ProviderInvalidResponseError,
    ProviderRequestError,
    ProviderTemporaryError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)

MESSAGES_PATH = "/v1/messages"
ANTHROPIC_API_VERSION = "2023-06-01"


class AnthropicProvider(SalesBriefProvider):
    name = "anthropic"

    def __init__(self, settings: Settings, *, client: httpx.Client | None = None) -> None:
        self._settings = settings
        self._owns_client = client is None
        # Deliberadamente SEM `base_url=` no client: um bug conhecido do
        # httpx (extração de cookies em `_send_single_request`) quebra a
        # composição de URL relativa contra `base_url` quando usado junto de
        # `httpx.MockTransport` — a URL completa é montada manualmente em
        # `generate()` em vez disso, mesmo padrão de
        # `app.domains.discovery.providers.google_places` (URLs absolutas).
        self._client = client or httpx.Client(
            timeout=httpx.Timeout(
                connect=settings.anthropic_http_connect_timeout_seconds,
                read=settings.anthropic_http_read_timeout_seconds,
                write=settings.anthropic_http_read_timeout_seconds,
                pool=settings.anthropic_http_connect_timeout_seconds,
            ),
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def is_configured(self) -> bool:
        return bool(self._settings.anthropic_api_key)

    def generate(self, *, system: str, user: str, max_tokens: int | None = None) -> ProviderResponse:
        if not self.is_configured():
            raise ProviderUnavailableError(
                "ANTHROPIC_API_KEY não configurada — provider anthropic indisponível. "
                "O Opportunity Score continua funcionando normalmente; só o Sales Brief "
                "fica indisponível até uma chave ser configurada."
            )

        body: dict[str, Any] = {
            "model": self._settings.anthropic_model,
            "max_tokens": max_tokens if max_tokens is not None else self._settings.anthropic_max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        headers = {
            "x-api-key": self._settings.anthropic_api_key or "",
            "anthropic-version": ANTHROPIC_API_VERSION,
            "content-type": "application/json",
        }

        url = f"{self._settings.anthropic_api_base_url.rstrip('/')}{MESSAGES_PATH}"
        started = time.monotonic()
        try:
            response = self._client.post(url, json=body, headers=headers)
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError(f"Timeout ao chamar a API da Anthropic: {exc.__class__.__name__}") from exc
        except httpx.TransportError as exc:
            raise ProviderRequestError(f"Falha de conexão ao chamar a API da Anthropic: {exc.__class__.__name__}") from exc
        duration_ms = (time.monotonic() - started) * 1000.0

        if response.status_code != 200:
            _raise_for_status(response)

        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderInvalidResponseError("Resposta da Anthropic não é um JSON válido.") from exc

        content_blocks = payload.get("content") or []
        text_parts = [block.get("text", "") for block in content_blocks if block.get("type") == "text"]
        text = "".join(text_parts).strip()
        if not text:
            raise ProviderInvalidResponseError("Resposta da Anthropic não contém nenhum bloco de texto.")

        usage = payload.get("usage") or {}

        return ProviderResponse(
            content=text,
            model=payload.get("model", self._settings.anthropic_model),
            duration_ms=duration_ms,
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
        )


def _raise_for_status(response: httpx.Response) -> None:
    status = response.status_code
    try:
        message = (response.json().get("error") or {}).get("message", response.text)
    except ValueError:
        message = response.text

    # A API key nunca aparece na URL nem no corpo — ainda assim, nunca
    # ecoamos headers da requisição na mensagem de erro, por segurança.
    safe_message = f"Anthropic respondeu {status}: {message}"[:500]

    if status == 429 or 500 <= status < 600:
        raise ProviderTemporaryError(safe_message)
    raise ProviderRequestError(safe_message, status_code=status)


__all__ = ["AnthropicProvider"]
