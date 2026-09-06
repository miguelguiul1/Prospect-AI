"""Provider da Google Places API (New).

Implementado contra a documentação oficial atual (não a Legacy API):

- Text Search (New): https://developers.google.com/maps/documentation/places/web-service/text-search
- Nearby Search (New): https://developers.google.com/maps/documentation/places/web-service/nearby-search
- Campos de dados e nível de SKU: https://developers.google.com/maps/documentation/places/web-service/data-fields
- Escolha de campos / FieldMask obrigatório: https://developers.google.com/maps/documentation/places/web-service/choose-fields

Text Search é usado quando a busca é por região/termo (`DiscoveryQuery` sem
latitude/longitude); Nearby Search é usado quando há um ponto geográfico e
raio — exatamente a divisão descrita na arquitetura da Fase 1, seção 7.
Nearby Search (New) não pagina (a documentação não descreve `nextPageToken`
para esse endpoint); Text Search (New) pagina via `nextPageToken`, até um
total documentado de 60 resultados.

Nenhum preço é assumido neste módulo. A tabela de campos abaixo anota o
nível de SKU (Essentials/Pro/Enterprise) só para leitura humana — o valor
monetário de cada nível não é hardcoded em lugar nenhum (ver
`Settings.discovery_cost_per_request` e `docs/discovery.md`).
"""
from __future__ import annotations

import time
from typing import Any

import httpx

from app.core.config import Settings
from app.core.logging import get_logger
from app.domains.discovery.dto import DiscoveredCompany
from app.domains.discovery.providers.base import DiscoveryProvider, ProviderPage
from app.domains.discovery.providers.errors import (
    ProviderRateLimitedError,
    ProviderRequestError,
    ProviderTemporaryError,
    ProviderUnavailableError,
)
from app.domains.discovery.providers.http_retry import call_with_retry
from app.domains.discovery.schemas import DiscoveryQuery

logger = get_logger(__name__)

TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
NEARBY_SEARCH_URL = "https://places.googleapis.com/v1/places:searchNearby"

# Campos mínimos necessários para o DTO de Discovery (app.domains.discovery.dto
# .DiscoveredCompany). Cada campo abaixo tem uma justificativa direta no DTO
# desta fase; nenhum é solicitado "porque pode ser útil depois" (ver seção 8
# do prompt de implementação da Fase 1). Comentado com o nível de SKU
# documentado por developers.google.com/.../data-fields, só como referência —
# não como preço.
_PLACE_FIELDS: list[str] = [
    "places.id",  # Essentials (IDs Only) — external_id / identidade da fonte
    "places.displayName",  # Pro — nome
    "places.formattedAddress",  # Pro (em busca) — endereço
    "places.location",  # Pro (em busca) — latitude/longitude
    "places.primaryType",  # Pro — categoria
    "places.businessStatus",  # Pro — aberto/fechado/etc.
    "places.googleMapsUri",  # Pro — source_url / URL de referência
    "places.internationalPhoneNumber",  # Enterprise — telefone comercial
    "places.websiteUri",  # Enterprise — site, só se a própria fonte fornecer
    "places.rating",  # Enterprise
    "places.userRatingCount",  # Enterprise
]

TEXT_SEARCH_FIELD_MASK = ",".join([*_PLACE_FIELDS, "nextPageToken"])
NEARBY_SEARCH_FIELD_MASK = ",".join(_PLACE_FIELDS)


class GooglePlacesProvider(DiscoveryProvider):
    name = "google_places"

    def __init__(self, settings: Settings, *, client: httpx.Client | None = None) -> None:
        self._settings = settings
        self._owns_client = client is None
        self._client = client or httpx.Client(
            timeout=httpx.Timeout(
                connect=settings.discovery_http_connect_timeout_seconds,
                read=settings.discovery_http_read_timeout_seconds,
                write=settings.discovery_http_read_timeout_seconds,
                pool=settings.discovery_http_connect_timeout_seconds,
            )
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def is_configured(self) -> bool:
        return bool(self._settings.google_maps_api_key)

    def search(self, query: DiscoveryQuery, *, page_token: str | None = None) -> ProviderPage:
        if not self.is_configured():
            raise ProviderUnavailableError(
                "GOOGLE_MAPS_API_KEY não configurada — provider google_places indisponível."
            )

        if query.uses_geographic_search():
            return self._search_nearby(query)
        return self._search_text(query, page_token=page_token)

    # -- Text Search -------------------------------------------------------

    def _search_text(self, query: DiscoveryQuery, *, page_token: str | None) -> ProviderPage:
        # A documentação exige que, ao paginar, todos os parâmetros além de
        # pageSize/pageToken permaneçam IDÊNTICOS à primeira chamada — por
        # isso o corpo é sempre reconstruído a partir da mesma `query`, só
        # acrescentando `pageToken` quando presente.
        body: dict[str, Any] = {
            "textQuery": query.build_text_query(),
            "pageSize": min(query.max_results, 20),
            "languageCode": query.language,
            "regionCode": query.country,
        }
        if page_token:
            body["pageToken"] = page_token

        def _do_request() -> httpx.Response:
            return self._client.post(
                TEXT_SEARCH_URL,
                json=body,
                headers=self._headers(TEXT_SEARCH_FIELD_MASK),
            )

        response = self._send(_do_request)
        payload = response.json()

        places = payload.get("places", [])
        results = [_map_place(place, source_url_field="googleMapsUri") for place in places]

        return ProviderPage(
            results=results,
            raw_result_count=len(places),
            operation="searchText",
            fields_requested=TEXT_SEARCH_FIELD_MASK.split(","),
            next_page_token=payload.get("nextPageToken"),
        )

    # -- Nearby Search -------------------------------------------------------

    def _search_nearby(self, query: DiscoveryQuery) -> ProviderPage:
        assert query.latitude is not None and query.longitude is not None and query.radius_km is not None

        body: dict[str, Any] = {
            "locationRestriction": {
                "circle": {
                    "center": {"latitude": query.latitude, "longitude": query.longitude},
                    "radius": query.radius_km * 1000.0,
                }
            },
            "maxResultCount": min(query.max_results, 20),
            "languageCode": query.language,
            "regionCode": query.country,
        }
        if query.business_types:
            body["includedTypes"] = query.business_types[:50]

        def _do_request() -> httpx.Response:
            return self._client.post(
                NEARBY_SEARCH_URL,
                json=body,
                headers=self._headers(NEARBY_SEARCH_FIELD_MASK),
            )

        response = self._send(_do_request)
        payload = response.json()

        places = payload.get("places", [])
        results = [_map_place(place, source_url_field="googleMapsUri") for place in places]

        return ProviderPage(
            results=results,
            raw_result_count=len(places),
            operation="searchNearby",
            fields_requested=NEARBY_SEARCH_FIELD_MASK.split(","),
            next_page_token=None,  # Nearby Search (New) não documenta paginação.
        )

    # -- Infra interna -------------------------------------------------------

    def _headers(self, field_mask: str) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self._settings.google_maps_api_key or "",
            "X-Goog-FieldMask": field_mask,
        }

    def _send(self, do_request: Any) -> httpx.Response:
        def _attempt() -> httpx.Response:
            try:
                response = do_request()
            except httpx.TimeoutException as exc:
                raise ProviderTemporaryError(f"Timeout ao chamar Google Places: {exc.__class__.__name__}") from exc
            except httpx.TransportError as exc:
                raise ProviderTemporaryError(
                    f"Falha de conexão ao chamar Google Places: {exc.__class__.__name__}"
                ) from exc

            if response.status_code == 200:
                return response

            _raise_for_status(response)
            raise AssertionError("unreachable")  # _raise_for_status sempre levanta

        return call_with_retry(
            _attempt,
            max_retries=self._settings.discovery_http_max_retries,
            backoff_base_seconds=self._settings.discovery_http_backoff_base_seconds,
            backoff_max_seconds=self._settings.discovery_http_backoff_max_seconds,
            sleep_fn=_default_sleep,
        )


def _default_sleep(seconds: float) -> None:
    time.sleep(seconds)


def _raise_for_status(response: httpx.Response) -> None:
    status = response.status_code

    try:
        error_body = response.json().get("error", {})
        message = error_body.get("message", response.text)
        google_status = error_body.get("status", "")
    except ValueError:
        message = response.text
        google_status = ""

    # A chave nunca aparece na URL nem no corpo de erro do Google (vai só no
    # header da requisição) — ainda assim, nunca ecoamos headers da
    # requisição na mensagem de erro, por segurança.
    safe_message = f"Google Places respondeu {status} ({google_status}): {message}"[:500]

    if status == 429:
        raise ProviderRateLimitedError(safe_message)
    if status in (401, 403):
        raise ProviderRequestError(safe_message, status_code=status)
    if status == 400:
        raise ProviderRequestError(safe_message, status_code=status)
    if 500 <= status < 600:
        raise ProviderTemporaryError(safe_message, status_code=status)

    raise ProviderRequestError(safe_message, status_code=status)


def _map_place(place: dict[str, Any], *, source_url_field: str) -> DiscoveredCompany:
    display_name = (place.get("displayName") or {}).get("text")
    location = place.get("location") or {}

    return DiscoveredCompany(
        source="google_places",
        external_id=place["id"],
        name=display_name,
        formatted_address=place.get("formattedAddress"),
        latitude=location.get("latitude"),
        longitude=location.get("longitude"),
        category=place.get("primaryType"),
        business_status=place.get("businessStatus"),
        phone=place.get("internationalPhoneNumber"),
        website=place.get("websiteUri"),
        rating=place.get("rating"),
        review_count=place.get("userRatingCount"),
        source_url=place.get(source_url_field),
        raw_reference=place,
    )
