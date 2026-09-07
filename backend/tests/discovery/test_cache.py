"""Testes de `app.domains.discovery.cache` (Prompt 10, seção 3 — auditoria
de cobertura).

Achado real: Redis nunca está disponível nesta suíte (porta morta desde
`conftest.py`), então TODO o caminho de sucesso deste módulo (cache hit,
deserialização, escrita) nunca havia sido exercitado por nenhum teste —
só o caminho "Redis indisponível" (fail-open) tinha cobertura, por ser o
único caminho que a suíte alcança naturalmente. Usa `fakeredis` (mesma
dependência de teste já trazida na Fase 8.2 para RQ) para exercitar o
caminho de sucesso de verdade, sem precisar de Redis real."""
from __future__ import annotations

from datetime import datetime, timezone

import fakeredis
import pytest

from app.domains.discovery import cache
from app.domains.discovery.dto import DiscoveredCompany
from app.domains.discovery.providers.base import ProviderPage
from app.domains.discovery.schemas import DiscoveryQuery


@pytest.fixture
def fake_redis(monkeypatch):
    connection = fakeredis.FakeStrictRedis()
    monkeypatch.setattr(cache, "get_redis_connection", lambda: connection)
    return connection


def _sample_page() -> ProviderPage:
    company = DiscoveredCompany(
        source="google_places",
        external_id="abc123",
        name="Padaria Central",
        city="São Paulo",
        collected_at=datetime(2026, 1, 15, 12, 30, tzinfo=timezone.utc),
    )
    return ProviderPage(
        results=[company],
        raw_result_count=1,
        operation="textsearch",
        fields_requested=["name", "city"],
        next_page_token="token-2",
    )


class TestBuildCacheKey:
    def test_same_inputs_produce_the_same_key(self) -> None:
        query = DiscoveryQuery(category="padaria", region="São Paulo")
        key_a = cache.build_cache_key("google_places", query, page_token=None)
        key_b = cache.build_cache_key("google_places", query, page_token=None)
        assert key_a == key_b

    def test_different_page_token_produces_a_different_key(self) -> None:
        query = DiscoveryQuery(category="padaria", region="São Paulo")
        key_a = cache.build_cache_key("google_places", query, page_token=None)
        key_b = cache.build_cache_key("google_places", query, page_token="next")
        assert key_a != key_b


class TestCacheRoundtrip:
    def test_set_then_get_returns_an_equivalent_page(self, fake_redis) -> None:
        page = _sample_page()
        key = "discovery:cache:test-roundtrip"

        cache.set_cached_page(key, page, ttl_seconds=3600)
        recovered = cache.get_cached_page(key)

        assert recovered is not None
        assert recovered.raw_result_count == 1
        assert recovered.operation == "textsearch"
        assert recovered.next_page_token == "token-2"
        assert len(recovered.results) == 1
        assert recovered.results[0].name == "Padaria Central"
        assert recovered.results[0].collected_at == datetime(2026, 1, 15, 12, 30, tzinfo=timezone.utc)

    def test_get_on_a_missing_key_returns_none(self, fake_redis) -> None:
        assert cache.get_cached_page("discovery:cache:does-not-exist") is None

    def test_set_respects_the_ttl(self, fake_redis) -> None:
        page = _sample_page()
        key = "discovery:cache:test-ttl"

        cache.set_cached_page(key, page, ttl_seconds=3600)

        assert fake_redis.ttl(key) > 0

    def test_get_on_a_corrupt_entry_returns_none_instead_of_raising(self, fake_redis) -> None:
        key = "discovery:cache:corrupt"
        fake_redis.set(key, b"isto nao e json valido {{{")

        assert cache.get_cached_page(key) is None


class TestCacheFailsOpenWhenRedisIsUnavailable:
    """Caminho já coberto antes desta fase, mantido para não regredir: sem
    Redis, o cache nunca derruba o Discovery."""

    def test_get_returns_none_when_redis_is_unreachable(self) -> None:
        assert cache.get_cached_page("qualquer-chave") is None

    def test_set_does_not_raise_when_redis_is_unreachable(self) -> None:
        cache.set_cached_page("qualquer-chave", _sample_page(), ttl_seconds=60)
