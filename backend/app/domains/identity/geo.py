"""Distância geográfica entre dois pontos, como sinal de apoio ao matching.

Implementado em Python puro (fórmula de Haversine) — sem PostGIS. A
arquitetura oficial é PostgreSQL simples (a imagem usada no
`docker-compose.yml` é `postgres:16-alpine`, sem a extensão PostGIS
provisionada); introduzir uma dependência de PostGIS agora exigiria
infraestrutura que não está disponível nem em produção nem localmente.
Como o Identity Resolution só compara um candidato contra um conjunto já
filtrado de empresas (`IdentityResolutionService.find_candidates`), não
contra a tabela inteira, calcular a distância em Python é suficiente nesta
escala. Migrar para `ST_DWithin`/PostGIS fica como otimização futura, não
uma mudança de arquitetura — ver docs/identity-resolution.md.
"""
from __future__ import annotations

import math

EARTH_RADIUS_METERS = 6_371_000.0


def haversine_distance_meters(
    lat1: float, lon1: float, lat2: float, lon2: float
) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return EARTH_RADIUS_METERS * c
