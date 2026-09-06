"""Testes do provider Google Places (New).

Nenhum destes testes chama a API real — todos usam `httpx.MockTransport`
para simular respostas determinísticas (arquitetura Fase 1, seção 26). O
teste de integração real, opcional e explicitamente marcado, está em
`test_google_places_live.py`.
"""
from __future__ import annotations

import json

import httpx
import pytest

from app.core.config import Settings
from app.domains.discovery.providers.errors import (
    ProviderRateLimitedError,
    ProviderRequestError,
    ProviderTemporaryError,
    ProviderUnavailableError,
)
from app.domains.discovery.providers.google_places import GooglePlacesProvider
from app.domains.discovery.schemas import DiscoveryQuery


def _settings(**overrides: object) -> Settings:
    defaults = dict(
        google_maps_api_key="test-key-not-real",
        discovery_http_max_retries=2,
        discovery_http_backoff_base_seconds=0.0,
        discovery_http_backoff_max_seconds=0.0,
    )
    defaults.update(overrides)
    return Settings(_env_file=None, **defaults)


def _provider(handler, **settings_overrides: object) -> GooglePlacesProvider:
    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    return GooglePlacesProvider(_settings(**settings_overrides), client=client)


def _place(place_id: str = "ChIJ_fake_1", *, name: str = "Restaurante Fake") -> dict:
    return {
        "id": place_id,
        "displayName": {"text": name, "languageCode": "pt-BR"},
        "formattedAddress": "Rua Fake, 123 - São Paulo, SP",
        "location": {"latitude": -23.68, "longitude": -46.7},
        "primaryType": "restaurant",
        "businessStatus": "OPERATIONAL",
        "googleMapsUri": f"https://maps.google.com/?cid={place_id}",
        "internationalPhoneNumber": "+55 11 91234-5678",
        "websiteUri": "https://restaurantefake.com.br",
        "rating": 4.5,
        "userRatingCount": 120,
    }


def _query(**overrides: object) -> DiscoveryQuery:
    defaults = dict(region="Interlagos", city="São Paulo", category="restaurantes")
    defaults.update(overrides)
    return DiscoveryQuery(**defaults)


class TestConfiguration:
    def test_is_configured_false_without_key(self) -> None:
        provider = GooglePlacesProvider(_settings(google_maps_api_key=None))

        assert provider.is_configured() is False

    def test_search_raises_provider_unavailable_without_key(self) -> None:
        provider = GooglePlacesProvider(_settings(google_maps_api_key=None))

        with pytest.raises(ProviderUnavailableError):
            provider.search(_query())


class TestTextSearchHappyPath:
    def test_valid_response_maps_to_discovered_companies(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url == httpx.URL("https://places.googleapis.com/v1/places:searchText")
            assert request.headers["X-Goog-Api-Key"] == "test-key-not-real"
            assert "places.id" in request.headers["X-Goog-FieldMask"]
            assert "nextPageToken" in request.headers["X-Goog-FieldMask"]
            return httpx.Response(200, json={"places": [_place()]})

        provider = _provider(handler)
        page = provider.search(_query())

        assert page.raw_result_count == 1
        assert page.operation == "searchText"
        assert page.next_page_token is None

        [result] = page.results
        assert result.source == "google_places"
        assert result.external_id == "ChIJ_fake_1"
        assert result.name == "Restaurante Fake"
        assert result.website == "https://restaurantefake.com.br"
        assert result.phone == "+55 11 91234-5678"
        assert result.rating == 4.5
        assert result.review_count == 120

    def test_empty_response_returns_empty_page(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"places": []})

        provider = _provider(handler)
        page = provider.search(_query())

        assert page.results == []
        assert page.raw_result_count == 0

    def test_missing_optional_fields_stay_none_not_negative(self) -> None:
        """Um resultado sem `websiteUri` deve virar `website=None` — nunca
        um valor que pareça uma afirmação de "não tem site" (essa é uma
        conclusão da auditoria, não do Discovery)."""
        bare_place = {
            "id": "ChIJ_bare",
            "displayName": {"text": "Empresa Sem Site"},
            "formattedAddress": "Rua X, 1",
            "location": {"latitude": -23.0, "longitude": -46.0},
        }

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"places": [bare_place]})

        provider = _provider(handler)
        [result] = provider.search(_query()).results

        assert result.website is None
        assert result.phone is None
        assert result.rating is None

    def test_pagination_token_is_forwarded_and_parsed(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            if "pageToken" in body:
                assert body["pageToken"] == "TOKEN_PAGE_2"
                return httpx.Response(200, json={"places": [_place("ChIJ_page2")]})
            return httpx.Response(200, json={"places": [_place("ChIJ_page1")], "nextPageToken": "TOKEN_PAGE_2"})

        provider = _provider(handler)

        first_page = provider.search(_query())
        assert first_page.next_page_token == "TOKEN_PAGE_2"

        second_page = provider.search(_query(), page_token=first_page.next_page_token)
        assert second_page.results[0].external_id == "ChIJ_page2"
        assert second_page.next_page_token is None


class TestNearbySearch:
    def test_geographic_query_uses_nearby_search(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url == httpx.URL("https://places.googleapis.com/v1/places:searchNearby")
            assert "nextPageToken" not in request.headers["X-Goog-FieldMask"]
            return httpx.Response(200, json={"places": [_place()]})

        provider = _provider(handler)
        page = provider.search(_query(region=None, city=None, latitude=-23.68, longitude=-46.7, radius_km=5))

        assert page.operation == "searchNearby"
        assert page.next_page_token is None


class TestErrorHandling:
    def test_400_raises_provider_request_error_without_retry(self) -> None:
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(1)
            return httpx.Response(400, json={"error": {"code": 400, "message": "Invalid textQuery", "status": "INVALID_ARGUMENT"}})

        provider = _provider(handler)

        with pytest.raises(ProviderRequestError):
            provider.search(_query())
        assert len(calls) == 1  # sem retry para erro permanente

    def test_401_raises_provider_request_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"error": {"code": 401, "message": "API key not valid", "status": "UNAUTHENTICATED"}})

        provider = _provider(handler)

        with pytest.raises(ProviderRequestError) as exc_info:
            provider.search(_query())
        assert "test-key-not-real" not in str(exc_info.value)

    def test_403_raises_provider_request_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(403, json={"error": {"code": 403, "message": "Permission denied", "status": "PERMISSION_DENIED"}})

        provider = _provider(handler)

        with pytest.raises(ProviderRequestError):
            provider.search(_query())

    def test_429_retries_then_raises_rate_limited(self) -> None:
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(1)
            return httpx.Response(429, json={"error": {"code": 429, "message": "Quota exceeded", "status": "RESOURCE_EXHAUSTED"}})

        provider = _provider(handler, discovery_http_max_retries=2)

        with pytest.raises(ProviderRateLimitedError):
            provider.search(_query())
        assert len(calls) == 3  # tentativa inicial + 2 retries

    def test_429_recovers_on_retry(self) -> None:
        responses = [
            httpx.Response(429, json={"error": {"code": 429, "message": "Quota exceeded", "status": "RESOURCE_EXHAUSTED"}}),
            httpx.Response(200, json={"places": [_place()]}),
        ]

        def handler(request: httpx.Request) -> httpx.Response:
            return responses.pop(0)

        provider = _provider(handler, discovery_http_max_retries=2)
        page = provider.search(_query())

        assert page.raw_result_count == 1

    def test_500_retries_then_raises_temporary_error(self) -> None:
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(1)
            return httpx.Response(500, json={"error": {"code": 500, "message": "Internal error", "status": "INTERNAL"}})

        provider = _provider(handler, discovery_http_max_retries=1)

        with pytest.raises(ProviderTemporaryError):
            provider.search(_query())
        assert len(calls) == 2  # tentativa inicial + 1 retry

    def test_timeout_is_retried_then_raises_temporary_error(self) -> None:
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(1)
            raise httpx.ReadTimeout("timed out", request=request)

        provider = _provider(handler, discovery_http_max_retries=1)

        with pytest.raises(ProviderTemporaryError):
            provider.search(_query())
        assert len(calls) == 2

    def test_connection_error_is_retryable(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused", request=request)

        provider = _provider(handler, discovery_http_max_retries=0)

        with pytest.raises(ProviderTemporaryError):
            provider.search(_query())
