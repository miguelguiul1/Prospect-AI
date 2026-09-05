"""Modelo de entrada de uma execução de descoberta.

`DiscoveryQuery` é a fronteira de validação do Discovery: nada chega a um
provider sem passar por aqui. Os limites definidos (raio, `max_results`,
`max_pages`) são limites INTERNOS nossos — não os da Google — para impedir
que um operador (ou um bug) gere uma quantidade ilimitada de chamadas
externas (arquitetura Fase 1, seção 3).
"""
from __future__ import annotations

import re
import unicodedata

from pydantic import BaseModel, Field, field_validator, model_validator

# Limites rígidos do próprio Discovery. Independem do provider e nunca são
# ultrapassados mesmo que `Settings.discovery_max_*_hard_cap` seja mal
# configurado — ver `DiscoveryQuery.max_results`/`max_pages`.
ABSOLUTE_MAX_RESULTS = 60
ABSOLUTE_MAX_PAGES = 3
MAX_RADIUS_KM = 50.0  # limite da própria Nearby Search (New): 50000 m.

_WHITESPACE_RE = re.compile(r"\s+")


def _clean_str(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    return _WHITESPACE_RE.sub(" ", normalized).strip()


class DiscoveryQuery(BaseModel):
    """Critérios de uma execução de descoberta, já validados.

    Use `latitude`/`longitude`/`radius_km` quando a busca tem uma área
    geográfica precisa (Nearby Search); use `region`/`city` quando a busca é
    por nome de lugar (Text Search) — ver `app.domains.discovery.service`
    para a escolha efetiva de operação.
    """

    region: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, max_length=120)
    state: str | None = Field(default=None, max_length=120)
    country: str = Field(default="BR", min_length=2, max_length=2)

    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    radius_km: float | None = Field(default=None, gt=0, le=MAX_RADIUS_KM)

    category: str = Field(..., min_length=1, max_length=120)
    business_types: list[str] = Field(default_factory=list, max_length=20)
    extra_terms: list[str] = Field(default_factory=list, max_length=10)

    max_results: int = Field(default=20, ge=1, le=ABSOLUTE_MAX_RESULTS)
    max_pages: int = Field(default=1, ge=1, le=ABSOLUTE_MAX_PAGES)

    language: str = Field(default="pt-BR", max_length=10)
    provider: str | None = Field(default=None, max_length=60)
    requested_by: str | None = Field(default=None, max_length=120)

    @field_validator("region", "city", "state", "category", mode="before")
    @classmethod
    def _clean_optional_text(cls, value: object) -> object:
        if value is None:
            return value
        if not isinstance(value, str):
            return value
        return _clean_str(value)

    @field_validator("country", mode="before")
    @classmethod
    def _upper_country(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().upper()
        return value

    @field_validator("business_types", "extra_terms", mode="before")
    @classmethod
    def _clean_string_list(cls, value: object) -> object:
        if not isinstance(value, list):
            return value
        cleaned = [_clean_str(item) for item in value if isinstance(item, str)]
        return [item for item in cleaned if item]

    @field_validator("category")
    @classmethod
    def _category_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("category não pode ser vazia")
        return value

    @model_validator(mode="after")
    def _validate_geography_and_intent(self) -> "DiscoveryQuery":
        has_lat = self.latitude is not None
        has_lng = self.longitude is not None

        if has_lat != has_lng:
            raise ValueError("latitude e longitude devem ser informadas juntas")

        if has_lat and has_lng:
            if self.radius_km is None:
                raise ValueError(
                    "radius_km é obrigatório quando latitude/longitude são informadas "
                    "(necessário para Nearby Search)"
                )
        else:
            if not self.region and not self.city:
                raise ValueError(
                    "informe region ou city quando latitude/longitude não forem usadas "
                    "(necessário para montar a Text Search)"
                )

        return self

    def uses_geographic_search(self) -> bool:
        return self.latitude is not None and self.longitude is not None

    def build_text_query(self) -> str:
        """Monta a string de busca usada pela Text Search a partir dos
        critérios já normalizados. Nunca chamado quando a busca é
        geográfica (`uses_geographic_search()` verdadeiro)."""
        parts = [self.category, *self.extra_terms]
        place_parts = [part for part in (self.city, self.region, self.state) if part]
        if place_parts:
            parts.append("em " + ", ".join(dict.fromkeys(place_parts)))
        return " ".join(parts).strip()
