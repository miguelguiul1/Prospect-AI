"""Modelo interno de um resultado descoberto (DTO), comum a qualquer
provider — o restante do Discovery (normalização, persistência) depende
somente deste contrato, nunca do formato bruto de uma fonte específica.

Regra central deste módulo: um campo ausente (`None`) significa apenas que
a fonte não forneceu aquele dado nesta chamada — nunca que o dado "não
existe". Essa conclusão pertence à auditoria digital (Fase 3), não ao
Discovery. Ver arquitetura v0.2, seção 06 do prompt da Fase 1.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class DiscoveredCompany:
    source: str
    external_id: str

    name: str | None = None
    formatted_address: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    latitude: float | None = None
    longitude: float | None = None

    category: str | None = None
    business_status: str | None = None

    phone: str | None = None
    website: str | None = None

    rating: float | None = None
    review_count: int | None = None

    source_url: str | None = None
    collected_at: datetime = field(default_factory=_now)

    raw_reference: dict | None = None
