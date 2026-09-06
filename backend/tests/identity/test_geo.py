from __future__ import annotations

import pytest

from app.domains.identity.geo import haversine_distance_meters


def test_same_point_has_zero_distance() -> None:
    assert haversine_distance_meters(-23.68, -46.7, -23.68, -46.7) == pytest.approx(0.0, abs=1e-6)


def test_known_distance_sao_paulo_to_rio() -> None:
    # Praça da Sé (SP) -> Cristo Redentor (RJ), ~357km em linha reta.
    distance = haversine_distance_meters(-23.5505, -46.6333, -22.9519, -43.2105)
    assert 350_000 < distance < 365_000


def test_nearby_points_within_a_block() -> None:
    # ~111m de diferença de latitude por 0.001 grau.
    distance = haversine_distance_meters(-23.5505, -46.6333, -23.5514, -46.6333)
    assert 90 < distance < 120
