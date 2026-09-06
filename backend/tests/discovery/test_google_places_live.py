"""Teste manual/opcional contra a API real do Google Places.

NÃO faz parte da suíte padrão. Só executa se:

1. a variável de ambiente `RUN_EXTERNAL_TESTS=1` estiver definida, e
2. `GOOGLE_MAPS_API_KEY` estiver configurada com uma chave real.

Nenhuma das duas está presente neste ambiente de desenvolvimento — este
teste está aqui para quem tiver uma chave própria e quiser validar a
integração de verdade. Ver docs/discovery.md, seção "Teste manual com uma
chave real".

Rodar explicitamente com:

    RUN_EXTERNAL_TESTS=1 pytest -m external tests/discovery/test_google_places_live.py
"""
from __future__ import annotations

import os

import pytest

from app.core.config import get_settings
from app.domains.discovery.providers.google_places import GooglePlacesProvider
from app.domains.discovery.schemas import DiscoveryQuery

pytestmark = pytest.mark.external

_SHOULD_RUN = os.environ.get("RUN_EXTERNAL_TESTS") == "1" and bool(os.environ.get("GOOGLE_MAPS_API_KEY"))


@pytest.mark.skipif(
    not _SHOULD_RUN,
    reason="Requer RUN_EXTERNAL_TESTS=1 e GOOGLE_MAPS_API_KEY reais — não roda por padrão.",
)
def test_real_text_search_returns_at_least_one_result() -> None:
    provider = GooglePlacesProvider(get_settings())
    query = DiscoveryQuery(region="Interlagos", city="São Paulo", category="restaurantes", max_results=5)

    page = provider.search(query)

    assert page.raw_result_count > 0
    assert page.results[0].external_id
