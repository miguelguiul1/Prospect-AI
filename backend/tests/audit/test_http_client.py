"""Testes de `fetch_safely` — nenhuma chamada de rede real: usa
`httpx.MockTransport` (mesmo padrão da Fase 1,
tests/discovery/test_google_places_provider.py) e injeta o resolver de DNS
via monkeypatch de `validate_url_is_safe` não é necessário aqui porque as
URLs de teste usam hostnames que resolvem para o IP público de exemplo via
um resolver fake passado através de `httpx.Client` — na verdade, como
`fetch_safely` chama `validate_url_is_safe` sem parâmetro de resolver, os
testes usam hostnames com IP literal (sempre público) para não depender de
DNS real.
"""
from __future__ import annotations

import httpx
import pytest

from app.core.config import Settings
from app.domains.audit.http_client import FetchError, fetch_safely
from app.domains.audit.ssrf import UnsafeURLError

# IP literal público (documentação, RFC 5737 TEST-NET-... na verdade é
# bloqueado — usamos um hostname que o próprio teste resolve via DNS real
# só nos testes de ssrf; aqui usamos IP literal genuinamente público para
# nunca depender de rede.
PUBLIC_URL = "http://93.184.216.34/"


def _settings(**overrides: object) -> Settings:
    defaults = dict(
        audit_http_max_redirects=3,
        audit_http_max_response_bytes=1000,
        audit_http_max_retries=1,
        audit_http_backoff_base_seconds=0.0,
        audit_http_backoff_max_seconds=0.0,
    )
    defaults.update(overrides)
    return Settings(_env_file=None, **defaults)


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)


class TestHappyPath:
    def test_200_response_is_returned(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.headers["User-Agent"]  # UA identificável sempre enviado
            return httpx.Response(200, headers={"content-type": "text/html"}, content=b"<html></html>")

        result = fetch_safely(PUBLIC_URL, settings=_settings(), client=_client(handler))

        assert result.status_code == 200
        assert result.final_url == PUBLIC_URL
        assert result.body == b"<html></html>"
        assert result.truncated is False
        assert result.redirect_chain == []

    def test_https_url_is_flagged(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, headers={"content-type": "text/html"}, content=b"ok")

        result = fetch_safely("https://93.184.216.34/", settings=_settings(), client=_client(handler))
        assert result.is_https is True


class TestRedirects:
    def test_follows_redirect_and_revalidates_ssrf(self) -> None:
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(str(request.url))
            if str(request.url) == PUBLIC_URL:
                return httpx.Response(302, headers={"location": "http://93.184.216.35/final"})
            return httpx.Response(200, headers={"content-type": "text/html"}, content=b"final page")

        result = fetch_safely(PUBLIC_URL, settings=_settings(), client=_client(handler))

        assert result.final_url == "http://93.184.216.35/final"
        assert result.redirect_chain == ["http://93.184.216.35/final"]
        assert len(calls) == 2

    def test_redirect_to_private_ip_is_blocked(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(302, headers={"location": "http://127.0.0.1/admin"})

        with pytest.raises(UnsafeURLError) as exc_info:
            fetch_safely(PUBLIC_URL, settings=_settings(), client=_client(handler))
        assert exc_info.value.reason == "blocked_ip"

    def test_too_many_redirects_raises_fetch_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(302, headers={"location": "http://93.184.216.34/loop"})

        with pytest.raises(FetchError) as exc_info:
            fetch_safely(PUBLIC_URL, settings=_settings(audit_http_max_redirects=2), client=_client(handler))
        assert exc_info.value.reason == "too_many_redirects"

    def test_redirect_without_location_header_raises_fetch_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(302)

        with pytest.raises(FetchError) as exc_info:
            fetch_safely(PUBLIC_URL, settings=_settings(), client=_client(handler))
        assert exc_info.value.reason == "redirect_without_location"


class TestResponseLimits:
    def test_response_larger_than_limit_is_truncated_not_rejected(self) -> None:
        big_body = b"x" * 5000

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, headers={"content-type": "text/html"}, content=big_body)

        result = fetch_safely(PUBLIC_URL, settings=_settings(audit_http_max_response_bytes=1000), client=_client(handler))

        assert result.truncated is True
        assert len(result.body) == 1000
        assert result.status_code == 200  # truncamento não vira erro


class TestErrorHandling:
    def test_timeout_raises_fetch_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("timed out", request=request)

        with pytest.raises(FetchError) as exc_info:
            fetch_safely(PUBLIC_URL, settings=_settings(audit_http_max_retries=0), client=_client(handler))
        assert exc_info.value.reason == "timeout"

    def test_connection_error_raises_fetch_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused", request=request)

        with pytest.raises(FetchError) as exc_info:
            fetch_safely(PUBLIC_URL, settings=_settings(audit_http_max_retries=0), client=_client(handler))
        assert exc_info.value.reason == "connection_failed"

    def test_transient_error_is_retried_then_succeeds(self) -> None:
        attempts = {"count": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise httpx.ConnectError("temporary", request=request)
            return httpx.Response(200, headers={"content-type": "text/html"}, content=b"ok")

        result = fetch_safely(PUBLIC_URL, settings=_settings(audit_http_max_retries=1), client=_client(handler))
        assert result.status_code == 200
        assert attempts["count"] == 2

    def test_404_is_returned_not_raised(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404, headers={"content-type": "text/html"}, content=b"not found")

        result = fetch_safely(PUBLIC_URL, settings=_settings(), client=_client(handler))
        assert result.status_code == 404  # servidor respondeu; não é um erro de transporte

    def test_500_is_returned_not_raised(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, content=b"internal error")

        result = fetch_safely(PUBLIC_URL, settings=_settings(), client=_client(handler))
        assert result.status_code == 500


class TestSSRFOnInitialUrl:
    def test_private_initial_url_is_blocked_before_any_request(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise AssertionError("não deveria enviar requisição nenhuma")

        with pytest.raises(UnsafeURLError):
            fetch_safely("http://127.0.0.1/", settings=_settings(), client=_client(handler))
