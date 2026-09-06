"""Integração ponta a ponta: duas execuções de Discovery, duas fontes
diferentes, mesma empresa no mundo real — o Identity Resolution (Fase 2)
deve reconhecer a segunda como a mesma `Company` da primeira, sem duplicar.

Nenhuma chamada de rede real — usa o mesmo `FakeProvider` dos testes da
Fase 1 (tests/discovery/test_service.py), só que com dois providers
representando duas fontes distintas.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.domains.companies.models import Company
from app.domains.discovery.dto import DiscoveredCompany
from app.domains.discovery.providers.base import DiscoveryProvider, ProviderPage
from app.domains.discovery.schemas import DiscoveryQuery
from app.domains.discovery.service import DiscoveryService
from app.domains.identity.models import CompanySource, DedupCandidate, DedupCandidateStatus


class _SinglePageProvider(DiscoveryProvider):
    def __init__(self, name: str, result: DiscoveredCompany) -> None:
        self.name = name
        self._result = result

    def is_configured(self) -> bool:
        return True

    def search(self, query: DiscoveryQuery, *, page_token: str | None = None) -> ProviderPage:
        return ProviderPage(results=[self._result], raw_result_count=1, operation="searchText")


def _query() -> DiscoveryQuery:
    return DiscoveryQuery(region="Interlagos", city="São Paulo", category="restaurantes")


def _settings() -> Settings:
    return Settings(_env_file=None, discovery_cost_per_request=None)


def test_two_sources_for_the_same_business_produce_one_company(db_session: Session) -> None:
    google_result = DiscoveredCompany(
        source="google_places",
        external_id="ChIJ_sao_joao",
        name="Restaurante São João",
        formatted_address="Rua das Flores, 100 - Centro",
        phone="+5511987654321",
    )
    google_provider = _SinglePageProvider("google_places", google_result)
    google_run = DiscoveryService(db_session, settings=_settings(), provider=google_provider)
    search_run_1 = google_run.start_run(_query())
    db_session.flush()
    google_run.execute(search_run_1.id)

    assert db_session.query(Company).count() == 1
    company_id = db_session.query(Company).one().id

    osm_result = DiscoveredCompany(
        source="openstreetmap",
        external_id="node/987654",
        name="REST. SAO JOAO",
        formatted_address="Rua das Flores 100 Centro",
        phone="+5511987654321",
    )
    osm_provider = _SinglePageProvider("openstreetmap", osm_result)
    osm_run = DiscoveryService(db_session, settings=_settings(), provider=osm_provider)
    search_run_2 = osm_run.start_run(_query())
    db_session.flush()
    osm_run.execute(search_run_2.id)

    # Nenhuma Company nova — a segunda fonte foi reconhecida como a mesma empresa.
    assert db_session.query(Company).count() == 1
    assert db_session.query(Company).one().id == company_id

    sources = db_session.query(CompanySource).filter(CompanySource.company_id == company_id).all()
    assert {s.source for s in sources} == {"google_places", "openstreetmap"}

    dedup_row = db_session.query(DedupCandidate).one()
    assert dedup_row.status == DedupCandidateStatus.AUTO_RESOLVED
    assert dedup_row.source == "openstreetmap"
    assert dedup_row.resulting_company_id == company_id


def test_two_unrelated_businesses_in_different_cities_stay_separate(db_session: Session) -> None:
    first = DiscoveredCompany(
        source="google_places", external_id="ChIJ_sp", name="Restaurante Central",
    )
    first_run = DiscoveryService(
        db_session, settings=_settings(), provider=_SinglePageProvider("google_places", first)
    )
    run_1 = first_run.start_run(DiscoveryQuery(region="Centro", city="São Paulo", category="restaurantes"))
    db_session.flush()
    first_run.execute(run_1.id)

    second = DiscoveredCompany(
        source="google_places", external_id="ChIJ_campinas", name="Restaurante Central",
    )
    second_run = DiscoveryService(
        db_session, settings=_settings(), provider=_SinglePageProvider("google_places", second)
    )
    run_2 = second_run.start_run(DiscoveryQuery(region="Centro", city="Campinas", category="restaurantes"))
    db_session.flush()
    second_run.execute(run_2.id)

    assert db_session.query(Company).count() == 2
