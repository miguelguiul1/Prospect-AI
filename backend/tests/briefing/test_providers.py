"""Testes de `AnthropicProvider` — sempre com `httpx.MockTransport`, nunca
uma chamada de rede real (a Fase 4 proíbe explicitamente chamar a API da
Anthropic de verdade "só para testar")."""
from __future__ import annotations

import json

import httpx
import pytest

from app.core.config import Settings
from app.domains.briefing.providers.anthropic_provider import AnthropicProvider
from app.domains.briefing.providers.errors import (
    ProviderInvalidResponseError,
    ProviderRequestError,
    ProviderTemporaryError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)


def _settings(**overrides) -> Settings:
    defaults = dict(_env_file=None, anthropic_api_key="sk-ant-test-key")
    defaults.update(overrides)
    return Settings(**defaults)


def _mock_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


class TestProviderUnavailable:
    def test_missing_api_key_raises_unavailable_without_any_network_call(self) -> None:
        called = False

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal called
            called = True
            return httpx.Response(200)

        provider = AnthropicProvider(_settings(anthropic_api_key=None), client=_mock_client(handler))
        assert provider.is_configured() is False

        with pytest.raises(ProviderUnavailableError):
            provider.generate(system="sys", user="usr")
        assert called is False


class TestProviderSuccess:
    def test_successful_call_returns_content_and_usage(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.headers["x-api-key"] == "sk-ant-test-key"
            assert request.headers["anthropic-version"] == "2023-06-01"
            return httpx.Response(
                200,
                json={
                    "model": "claude-sonnet-4-5-20250929",
                    "content": [{"type": "text", "text": '{"summary": "ok"}'}],
                    "usage": {"input_tokens": 120, "output_tokens": 45},
                },
            )

        provider = AnthropicProvider(_settings(), client=_mock_client(handler))
        response = provider.generate(system="sys", user="usr")

        assert response.content == '{"summary": "ok"}'
        assert response.model == "claude-sonnet-4-5-20250929"
        assert response.input_tokens == 120
        assert response.output_tokens == 45
        assert response.duration_ms >= 0.0

    def test_never_invents_token_usage_when_not_provided(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"model": "m", "content": [{"type": "text", "text": "ok"}]})

        provider = AnthropicProvider(_settings(), client=_mock_client(handler))
        response = provider.generate(system="sys", user="usr")

        assert response.input_tokens is None
        assert response.output_tokens is None


class TestProviderFailures:
    def test_timeout_raises_provider_timeout_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.TimeoutException("timed out", request=request)

        provider = AnthropicProvider(_settings(), client=_mock_client(handler))
        with pytest.raises(ProviderTimeoutError):
            provider.generate(system="sys", user="usr")

    def test_connection_failure_raises_provider_request_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("recusado", request=request)

        provider = AnthropicProvider(_settings(), client=_mock_client(handler))
        with pytest.raises(ProviderRequestError):
            provider.generate(system="sys", user="usr")

    def test_401_raises_provider_request_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"error": {"message": "invalid x-api-key"}})

        provider = AnthropicProvider(_settings(), client=_mock_client(handler))
        with pytest.raises(ProviderRequestError):
            provider.generate(system="sys", user="usr")

    def test_429_raises_provider_temporary_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(429, json={"error": {"message": "rate limited"}})

        provider = AnthropicProvider(_settings(), client=_mock_client(handler))
        with pytest.raises(ProviderTemporaryError):
            provider.generate(system="sys", user="usr")

    def test_5xx_raises_provider_temporary_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={"error": {"message": "internal"}})

        provider = AnthropicProvider(_settings(), client=_mock_client(handler))
        with pytest.raises(ProviderTemporaryError):
            provider.generate(system="sys", user="usr")

    def test_response_without_text_block_raises_invalid_response_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"model": "m", "content": []})

        provider = AnthropicProvider(_settings(), client=_mock_client(handler))
        with pytest.raises(ProviderInvalidResponseError):
            provider.generate(system="sys", user="usr")

    def test_non_json_response_body_raises_invalid_response_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"not json at all")

        provider = AnthropicProvider(_settings(), client=_mock_client(handler))
        with pytest.raises(ProviderInvalidResponseError):
            provider.generate(system="sys", user="usr")

    def test_api_key_never_appears_in_error_message(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(403, json={"error": {"message": "forbidden"}})

        provider = AnthropicProvider(_settings(anthropic_api_key="super-secret-key"), client=_mock_client(handler))
        with pytest.raises(ProviderRequestError) as exc_info:
            provider.generate(system="sys", user="usr")
        assert "super-secret-key" not in str(exc_info.value)
