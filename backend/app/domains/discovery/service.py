"""Orquestração do Discovery: SearchRun -> provider -> normalização ->
persistência -> rastreabilidade.

`DiscoveryService` é o único ponto que decide o ciclo de vida de um
`SearchRun`. Ele depende da interface `DiscoveryProvider`
(app.domains.discovery.providers.base), nunca de uma implementação
concreta — o provider é resolvido pelo nome guardado no próprio
`SearchRun` (`app.domains.discovery.providers.get_provider`).

Não implementa: Identity Resolution (fusão de candidatos ambíguos),
Digital Audit, scoring ou qualquer geração de briefing — apenas descoberta,
normalização e persistência de candidatos, conforme a Fase 1.
"""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.domains.discovery import cache
from app.domains.discovery.models import ProviderUsageRecord, SearchRun, SearchRunStatus
from app.domains.discovery.persistence import (
    find_or_create_category,
    find_or_create_company,
    find_or_create_region,
    record_evidence,
)
from app.domains.discovery.providers import get_provider
from app.domains.discovery.providers.base import DiscoveryProvider, ProviderPage
from app.domains.discovery.providers.errors import DiscoveryProviderError
from app.domains.discovery.schemas import DiscoveryQuery
from app.domains.identity.service import IdentityResolutionService

logger = get_logger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class DiscoveryService:
    def __init__(self, db: Session, *, settings: Settings | None = None, provider: DiscoveryProvider | None = None):
        self._db = db
        self._settings = settings or get_settings()
        self._injected_provider = provider

    # -- Ciclo de vida do SearchRun -------------------------------------

    def start_run(self, query: DiscoveryQuery) -> SearchRun:
        """Cria o `SearchRun` em `PENDING`. Não executa a busca — isso é
        `execute()`, tipicamente chamado por um job (ver
        app.domains.discovery.jobs)."""
        provider_name = query.provider or self._settings.discovery_provider

        if query.uses_geographic_search():
            region_label = f"{query.latitude},{query.longitude} (raio {query.radius_km}km)"
        else:
            region_label = query.region or query.city or ""

        search_run = SearchRun(
            region_query=region_label,
            segment_query=query.category,
            provider=provider_name,
            parameters=query.model_dump(mode="json"),
            status=SearchRunStatus.PENDING,
            requested_by=query.requested_by,
            cost_currency=self._settings.discovery_cost_currency,
        )
        self._db.add(search_run)
        self._db.flush()
        return search_run

    def execute(self, search_run_id: uuid.UUID) -> SearchRun:
        search_run = self._db.get(SearchRun, search_run_id)
        if search_run is None:
            raise ValueError(f"SearchRun {search_run_id} não encontrado")

        query = DiscoveryQuery.model_validate(search_run.parameters)

        search_run.status = SearchRunStatus.RUNNING
        search_run.started_at = _now()
        self._db.flush()

        try:
            provider = self._injected_provider or get_provider(search_run.provider, self._settings)
        except DiscoveryProviderError as exc:
            self._fail_run(search_run, exc, persisted_so_far=0)
            return search_run

        if not provider.is_configured():
            self._fail_run(
                search_run,
                RuntimeError(f"Provider '{search_run.provider}' não está configurado."),
                persisted_so_far=0,
            )
            return search_run

        raw_count = 0
        normalized_count = 0
        persisted_count = 0
        new_company_count = 0
        pages_fetched = 0
        page_token: str | None = None
        category = find_or_create_category(self._db, query.category)
        region = find_or_create_region(self._db, query)
        identity_service = IdentityResolutionService(self._db, settings=self._settings)

        try:
            while True:
                page = self._fetch_page(provider, query, page_token=page_token, search_run=search_run)
                pages_fetched += 1
                raw_count += page.raw_result_count

                remaining = query.max_results - persisted_count
                results = page.results[: max(remaining, 0)]

                for discovered in results:
                    normalized_count += 1
                    company, created = find_or_create_company(
                        self._db, discovered, region=region, category=category,
                        identity_service=identity_service,
                    )
                    record_evidence(self._db, company, discovered)
                    persisted_count += 1
                    if created:
                        new_company_count += 1

                self._db.flush()

                page_token = page.next_page_token
                reached_result_cap = persisted_count >= query.max_results
                reached_page_cap = pages_fetched >= query.max_pages
                if not page_token or reached_result_cap or reached_page_cap:
                    break

                if self._settings.discovery_page_token_delay_seconds > 0:
                    time.sleep(self._settings.discovery_page_token_delay_seconds)

        except DiscoveryProviderError as exc:
            self._finish_run(
                search_run,
                status=SearchRunStatus.PARTIALLY_COMPLETED if persisted_count > 0 else SearchRunStatus.FAILED,
                raw_count=raw_count,
                normalized_count=normalized_count,
                persisted_count=persisted_count,
                new_company_count=new_company_count,
                pages_fetched=pages_fetched,
                error=exc,
            )
            return search_run

        self._finish_run(
            search_run,
            status=SearchRunStatus.COMPLETED,
            raw_count=raw_count,
            normalized_count=normalized_count,
            persisted_count=persisted_count,
            new_company_count=new_company_count,
            pages_fetched=pages_fetched,
            error=None,
        )
        return search_run

    # -- Internos -----------------------------------------------------------

    def _fetch_page(
        self,
        provider: DiscoveryProvider,
        query: DiscoveryQuery,
        *,
        page_token: str | None,
        search_run: SearchRun,
    ) -> ProviderPage:
        cache_key = cache.build_cache_key(provider.name, query, page_token=page_token)
        cached = cache.get_cached_page(cache_key)
        if cached is not None:
            logger.info("discovery_cache_hit", search_run_id=str(search_run.id), provider=provider.name)
            return cached

        page = provider.search(query, page_token=page_token)

        cache.set_cached_page(cache_key, page, ttl_seconds=self._settings.discovery_cache_ttl_seconds)
        self._record_usage(search_run, page)
        return page

    def _record_usage(self, search_run: SearchRun, page: ProviderPage) -> None:
        cost = self._settings.discovery_cost_per_request
        usage = ProviderUsageRecord(
            search_run_id=search_run.id,
            provider=search_run.provider,
            operation=page.operation,
            fields_requested=page.fields_requested,
            result_count=page.raw_result_count,
            estimated_cost=cost,
            currency=self._settings.discovery_cost_currency if cost is not None else None,
        )
        self._db.add(usage)
        self._db.flush()

    def _fail_run(self, search_run: SearchRun, exc: Exception, *, persisted_so_far: int) -> None:
        self._finish_run(
            search_run,
            status=SearchRunStatus.FAILED,
            raw_count=0,
            normalized_count=0,
            persisted_count=persisted_so_far,
            new_company_count=0,
            pages_fetched=0,
            error=exc,
        )

    def _finish_run(
        self,
        search_run: SearchRun,
        *,
        status: SearchRunStatus,
        raw_count: int,
        normalized_count: int,
        persisted_count: int,
        new_company_count: int,
        pages_fetched: int,
        error: Exception | None,
    ) -> None:
        search_run.status = status
        search_run.raw_result_count = raw_count
        search_run.normalized_result_count = normalized_count
        search_run.persisted_count = persisted_count
        search_run.new_company_count = new_company_count
        search_run.pages_fetched = pages_fetched
        search_run.finished_at = _now()

        if error is not None:
            search_run.error_code = error.__class__.__name__
            search_run.error_message = str(error)[:500]
            logger.warning(
                "discovery_run_finished_with_error",
                search_run_id=str(search_run.id),
                status=status.value,
                error_code=search_run.error_code,
            )
        else:
            logger.info(
                "discovery_run_completed",
                search_run_id=str(search_run.id),
                status=status.value,
                persisted_count=persisted_count,
            )

        total_cost = self._db.query(ProviderUsageRecord).filter(
            ProviderUsageRecord.search_run_id == search_run.id
        ).all()
        costs = [record.estimated_cost for record in total_cost if record.estimated_cost is not None]
        search_run.cost_estimate = sum(costs) if costs else None

        self._db.flush()


__all__ = ["DiscoveryService"]
