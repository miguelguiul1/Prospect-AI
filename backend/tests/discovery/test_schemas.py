"""Validação de `DiscoveryQuery` — a fronteira de entrada do Discovery.

Nenhum destes testes chama uma fonte externa: são só regras de validação
(arquitetura Fase 1, seção 3).
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.domains.discovery.schemas import DiscoveryQuery


def test_valid_text_search_query() -> None:
    query = DiscoveryQuery(region="Interlagos", city="São Paulo", category="restaurantes")

    assert query.uses_geographic_search() is False
    assert "restaurantes" in query.build_text_query()


def test_valid_geographic_query() -> None:
    query = DiscoveryQuery(latitude=-23.68, longitude=-46.7, radius_km=5, category="restaurantes")

    assert query.uses_geographic_search() is True


def test_category_cannot_be_blank() -> None:
    with pytest.raises(ValidationError):
        DiscoveryQuery(region="Interlagos", category="   ")


def test_latitude_without_longitude_is_rejected() -> None:
    with pytest.raises(ValidationError):
        DiscoveryQuery(latitude=-23.68, category="restaurantes")


def test_geographic_query_requires_radius() -> None:
    with pytest.raises(ValidationError):
        DiscoveryQuery(latitude=-23.68, longitude=-46.7, category="restaurantes")


def test_text_query_requires_region_or_city() -> None:
    with pytest.raises(ValidationError):
        DiscoveryQuery(category="restaurantes")


@pytest.mark.parametrize("radius_km", [0, -1, 50.1, 1000])
def test_radius_out_of_bounds_is_rejected(radius_km: float) -> None:
    with pytest.raises(ValidationError):
        DiscoveryQuery(latitude=-23.68, longitude=-46.7, radius_km=radius_km, category="restaurantes")


@pytest.mark.parametrize("max_results", [0, -1, 61, 1000])
def test_max_results_hard_cap_cannot_be_exceeded(max_results: int) -> None:
    with pytest.raises(ValidationError):
        DiscoveryQuery(region="Interlagos", category="restaurantes", max_results=max_results)


@pytest.mark.parametrize("max_pages", [0, -1, 4, 100])
def test_max_pages_hard_cap_cannot_be_exceeded(max_pages: int) -> None:
    with pytest.raises(ValidationError):
        DiscoveryQuery(region="Interlagos", category="restaurantes", max_pages=max_pages)


def test_latitude_and_longitude_ranges_are_enforced() -> None:
    with pytest.raises(ValidationError):
        DiscoveryQuery(latitude=200, longitude=-46.7, radius_km=5, category="restaurantes")


def test_whitespace_and_unicode_are_normalized() -> None:
    query = DiscoveryQuery(region="  Interlagos   ", category="  Restaurantes  ")

    assert query.region == "Interlagos"
    assert query.category == "Restaurantes"


def test_country_is_uppercased() -> None:
    query = DiscoveryQuery(region="Interlagos", category="restaurantes", country="br")

    assert query.country == "BR"
