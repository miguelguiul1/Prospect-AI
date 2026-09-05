"""Testes de integração local do `DiscoveryService`.

Usam um provider falso (`FakeProvider`), nunca a API real — cobrem o
ciclo `SearchRun -> provider -> normalização -> persistência`. O banco é o
SQLite de teste real (via `db_session`, ver conftest.py), não um mock.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.domains.companies.models import Company
from app.domains.discovery.dto import DiscoveredCompany
from app.domains.discovery.models import ProviderUsageRecord, SearchRun, SearchRunStatus
from app.domains.discovery.providers.base import DiscoveryProvider, ProviderPage
from app.domains.discovery.providers.errors import ProviderRateLimitedError
from app.domains.discovery.schemas import DiscoveryQuery
from app.domains.discovery.service import DiscoveryService
from app.domains.evidence.models import Evidence
from app.domains.identity.models import CompanySource


class FakeProvider(DiscoveryProvider):
    """Provider de teste: devolve páginas pré-programadas em sequência, sem
    nenhuma chamada de rede."""

    name = "fake_provider"

    def __init__(self, pages: list[ProviderPage], *, configured: bool = True) -> None:
        self._pages = list(pages)
        self._configured = configured
        self.calls: list[str | None] = []

    def is_configured(self) -> bool:
        return self._configured

    def search(self, query: DiscoveryQuery, *, page_token: str | None = None) -> ProviderPage:
        self.calls.append(page_token)
        if not self._pages:
            raise AssertionError("FakeProvider esgotado — teste pediu mais páginas do que programou")
        return self._pages.pop(0)


def _discovered(external_id: str, **overrides: object) -> DiscoveredCompany:
    defaults = dict(
        source="fake_provider",
        external_id=external_id,
        name=f"Empresa {external_id}",
        formatted_address="Rua Teste, 1",
        phone="+5511987654321",
        website="https://empresa.example.com",
        category="restaurant",
        business_status="OPERATIONAL",
        rating=4.2,
        review_count=10,
        source_url=f"https://maps.example.com/{external_id}",
        raw_reference={"id": external_id},
    )
    defaults.update(overrides)
    return DiscoveredCompany(**defaults)


def _query(**overrides: object) -> DiscoveryQuery:
    defaults = dict(region="Interlagos", city="São Paulo", category="restaurantes", max_results=20, max_pages=2)
    defaults.update(overrides)
    return DiscoveryQuery(**defaults)


def _page(results: list[DiscoveredCompany], *, next_page_token: str | None = None) -> ProviderPage:
    return ProviderPage(
        results=results,
        raw_result_count=len(results),
        operation="searchText",
        fields_requested=["places.id"],
        next_page_token=next_page_token,
    )


def _settings_no_cost() -> Settings:
    return Settings(_env_file=None, discovery_cost_per_request=None)


class TestSuccessfulRun:
    def test_run_completes_and_persists_company_and_source(self, db_session: Session) -> None:
        provider = FakeProvider([_page([_discovered("A1")])])
        service = DiscoveryService(db_session, settings=_settings_no_cost(), provider=provider)

        search_run = service.start_run(_query())
        db_session.flush()
        service.execute(search_run.id)

        assert search_run.status == SearchRunStatus.COMPLETED
        assert search_run.persisted_count == 1
        assert search_run.new_company_count == 1
        assert search_run.raw_result_count == 1

        company = db_session.query(Company).one()
        assert company.canonical_name == "Empresa A1"

        source = db_session.query(CompanySource).one()
        assert source.source == "fake_provider"
        assert source.external_id == "A1"
        assert source.company_id == company.id

    def test_evidence_is_recorded_with_provenance(self, db_session: Session) -> None:
        provider = FakeProvider([_page([_discovered("A1")])])
        service = DiscoveryService(db_session, settings=_settings_no_cost(), provider=provider)

        search_run = service.start_run(_query())
        db_session.flush()
        service.execute(search_run.id)

        evidences = db_session.query(Evidence).all()
        fields = {e.field: e for e in evidences}

        assert "website" in fields
        assert fields["website"].value == "https://empresa.example.com"
        assert fields["website"].source == "fake_provider"
        assert fields["website"].confidence.value == "high"
        assert fields["website"].method.value == "structured_field"

    def test_never_creates_evidence_for_absent_fields(self, db_session: Session) -> None:
        """Se a fonte não trouxe telefone, nenhuma Evidence de `phone` deve
        existir — nunca uma evidência que pareça dizer "não tem telefone"."""
        provider = FakeProvider([_page([_discovered("A1", phone=None, website=None)])])
        service = DiscoveryService(db_session, settings=_settings_no_cost(), provider=provider)

        search_run = service.start_run(_query())
        db_session.flush()
        service.execute(search_run.id)

        fields = {e.field for e in db_session.query(Evidence).all()}
        assert "phone" not in fields
        assert "website" not in fields

    def test_multiple_results_create_multiple_companies(self, db_session: Session) -> None:
        provider = FakeProvider([_page([_discovered("A1"), _discovered("A2"), _discovered("A3")])])
        service = DiscoveryService(db_session, settings=_settings_no_cost(), provider=provider)

        search_run = service.start_run(_query())
        db_session.flush()
        service.execute(search_run.id)

        assert db_session.query(Company).count() == 3
        assert db_session.query(CompanySource).count() == 3
        assert search_run.persisted_count == 3

    def test_pagination_follows_next_page_token_until_exhausted(self, db_session: Session) -> None:
        provider = FakeProvider(
            [
                _page([_discovered("A1")], next_page_token="TOKEN_2"),
                _page([_discovered("A2")], next_page_token=None),
            ]
        )
        service = DiscoveryService(db_session, settings=_settings_no_cost(), provider=provider)

        search_run = service.start_run(_query(max_pages=2))
        db_session.flush()
        service.execute(search_run.id)

        assert search_run.pages_fetched == 2
        assert search_run.persisted_count == 2
        assert provider.calls == [None, "TOKEN_2"]

    def test_stops_at_max_pages_even_if_more_tokens_available(self, db_session: Session) -> None:
        provider = FakeProvider(
            [
                _page([_discovered("A1")], next_page_token="TOKEN_2"),
            ]
        )
        service = DiscoveryService(db_session, settings=_settings_no_cost(), provider=provider)

        search_run = service.start_run(_query(max_pages=1))
        db_session.flush()
        service.execute(search_run.id)

        assert search_run.pages_fetched == 1
        assert search_run.status == SearchRunStatus.COMPLETED  # limite nosso, não é uma falha


class TestReprocessingIsAppendOnly:
    def test_rerun_with_identical_data_does_not_duplicate_evidence(self, db_session: Session) -> None:
        query = _query()

        provider_1 = FakeProvider([_page([_discovered("A1")])])
        service_1 = DiscoveryService(db_session, settings=_settings_no_cost(), provider=provider_1)
        run_1 = service_1.start_run(query)
        db_session.flush()
        service_1.execute(run_1.id)

        provider_2 = FakeProvider([_page([_discovered("A1")])])
        service_2 = DiscoveryService(db_session, settings=_settings_no_cost(), provider=provider_2)
        run_2 = service_2.start_run(query)
        db_session.flush()
        service_2.execute(run_2.id)

        assert db_session.query(Company).count() == 1  # mesma fonte, mesma empresa
        website_evidences = db_session.query(Evidence).filter(Evidence.field == "website").all()
        assert len(website_evidences) == 1  # valor não mudou: nenhuma linha nova

    def test_rerun_with_changed_value_supersedes_old_evidence(self, db_session: Session) -> None:
        query = _query()

        provider_1 = FakeProvider([_page([_discovered("A1", website="https://old.example.com")])])
        service_1 = DiscoveryService(db_session, settings=_settings_no_cost(), provider=provider_1)
        run_1 = service_1.start_run(query)
        db_session.flush()
        service_1.execute(run_1.id)

        provider_2 = FakeProvider([_page([_discovered("A1", website="https://new.example.com")])])
        service_2 = DiscoveryService(db_session, settings=_settings_no_cost(), provider=provider_2)
        run_2 = service_2.start_run(query)
        db_session.flush()
        service_2.execute(run_2.id)

        website_evidences = (
            db_session.query(Evidence).filter(Evidence.field == "website").order_by(Evidence.collected_at).all()
        )
        assert len(website_evidences) == 2
        old, new = website_evidences
        assert old.superseded_by_id == new.id
        assert old.value == "https://old.example.com"
        assert new.value == "https://new.example.com"


class TestControlledFailures:
    def test_provider_not_configured_fails_run_without_crashing(self, db_session: Session) -> None:
        provider = FakeProvider([], configured=False)
        service = DiscoveryService(db_session, settings=_settings_no_cost(), provider=provider)

        search_run = service.start_run(_query())
        db_session.flush()
        service.execute(search_run.id)  # não deve levantar exceção

        assert search_run.status == SearchRunStatus.FAILED
        assert search_run.error_message is not None
        assert db_session.query(Company).count() == 0

    def test_rate_limit_after_partial_results_marks_partially_completed(self, db_session: Session) -> None:
        class RateLimitedAfterFirstPage(FakeProvider):
            def search(self, query: DiscoveryQuery, *, page_token: str | None = None) -> ProviderPage:
                if page_token is None:
                    return _page([_discovered("A1")], next_page_token="TOKEN_2")
                raise ProviderRateLimitedError("limite excedido")

        provider = RateLimitedAfterFirstPage([])
        service = DiscoveryService(db_session, settings=_settings_no_cost(), provider=provider)

        search_run = service.start_run(_query(max_pages=2))
        db_session.flush()
        service.execute(search_run.id)

        assert search_run.status == SearchRunStatus.PARTIALLY_COMPLETED
        assert search_run.persisted_count == 1
        assert search_run.error_code == "ProviderRateLimitedError"
        assert db_session.query(Company).count() == 1

    def test_rate_limit_on_first_page_marks_failed_not_partial(self, db_session: Session) -> None:
        class AlwaysRateLimited(FakeProvider):
            def search(self, query: DiscoveryQuery, *, page_token: str | None = None) -> ProviderPage:
                raise ProviderRateLimitedError("limite excedido")

        provider = AlwaysRateLimited([])
        service = DiscoveryService(db_session, settings=_settings_no_cost(), provider=provider)

        search_run = service.start_run(_query())
        db_session.flush()
        service.execute(search_run.id)

        assert search_run.status == SearchRunStatus.FAILED
        assert search_run.persisted_count == 0

    def test_unknown_search_run_id_raises_value_error(self, db_session: Session) -> None:
        service = DiscoveryService(db_session, settings=_settings_no_cost(), provider=FakeProvider([]))

        with pytest.raises(ValueError):
            service.execute(uuid.uuid4())


class TestUsageTracking:
    def test_one_usage_record_per_provider_call(self, db_session: Session) -> None:
        provider = FakeProvider(
            [
                _page([_discovered("A1")], next_page_token="TOKEN_2"),
                _page([_discovered("A2")]),
            ]
        )
        service = DiscoveryService(db_session, settings=_settings_no_cost(), provider=provider)

        search_run = service.start_run(_query(max_pages=2))
        db_session.flush()
        service.execute(search_run.id)

        usage_records = db_session.query(ProviderUsageRecord).filter(
            ProviderUsageRecord.search_run_id == search_run.id
        ).all()
        assert len(usage_records) == 2
        assert all(record.estimated_cost is None for record in usage_records)
        assert search_run.cost_estimate is None

    def test_cost_is_estimated_when_price_is_configured(self, db_session: Session) -> None:
        provider = FakeProvider([_page([_discovered("A1")])])
        settings = Settings(_env_file=None, discovery_cost_per_request=0.017, discovery_cost_currency="USD")
        service = DiscoveryService(db_session, settings=settings, provider=provider)

        search_run = service.start_run(_query())
        db_session.flush()
        service.execute(search_run.id)

        assert search_run.cost_estimate == pytest.approx(0.017)
        assert search_run.cost_currency == "USD"
