"""Testes de `app.domains.companies.queries` — as consultas agregadas de
leitura usadas pelo Dashboard (Fase 5). Nenhum cálculo de negócio é
exercitado aqui além do que já é coberto pelos testes das Fases 3/4; estes
testes provam que a consulta agregada devolve exatamente o que foi
persistido, sem recalcular nada.
"""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.domains.audit.enums import AuditStatus
from app.domains.audit.models import AuditSnapshot, WebsiteQuality
from app.domains.briefing.models import SalesBrief, SalesBriefStatus
from app.domains.companies.models import Category, Company, Region
from app.domains.companies.queries import get_company_detail, get_dashboard_stats, list_companies
from app.domains.evidence.enums import ConfidenceLevel, DataState, EvidenceMethod
from app.domains.evidence.models import Evidence
from app.domains.identity.models import CompanySource
from app.domains.scoring.models import OpportunityScore, OpportunityTier


def _company(db: Session, *, name: str = "Barbearia Exemplo", category_slug: str | None = None, region_name: str | None = None) -> Company:
    category = None
    if category_slug:
        category = Category(slug=category_slug, name=category_slug.capitalize())
        db.add(category)
        db.flush()
    region = None
    if region_name:
        region = Region(name=region_name, country="BR")
        db.add(region)
        db.flush()
    company = Company(canonical_name=name, category_id=category.id if category else None, region_id=region.id if region else None)
    db.add(company)
    db.flush()
    return company


def _audited(db: Session, company: Company, *, site_state: DataState, quality_score: float | None = None,
             opportunity_score: float | None = None, tier: OpportunityTier | None = None) -> AuditSnapshot:
    snapshot = AuditSnapshot(company_id=company.id, run_id=uuid.uuid4(), status=AuditStatus.COMPLETED, site_state=site_state)
    db.add(snapshot)
    db.flush()
    if quality_score is not None:
        db.add(WebsiteQuality(audit_snapshot_id=snapshot.id, score=quality_score, confidence=ConfidenceLevel.HIGH))
    if opportunity_score is not None:
        db.add(
            OpportunityScore(
                audit_snapshot_id=snapshot.id, score=opportunity_score, tier=tier,
                confidence=ConfidenceLevel.HIGH, scoring_version="v1", breakdown={},
            )
        )
    db.flush()
    return snapshot


class TestListCompanies:
    def test_empty_database_returns_empty_page(self, db_session: Session) -> None:
        page = list_companies(db_session)
        assert page.items == []
        assert page.total == 0

    def test_company_without_audit_appears_with_nulls(self, db_session: Session) -> None:
        _company(db_session, name="Sem Auditoria")

        page = list_companies(db_session)

        assert page.total == 1
        item = page.items[0]
        assert item.has_audit is False
        assert item.site_state is None
        assert item.opportunity_score is None

    def test_company_with_audit_and_score_appears_populated(self, db_session: Session) -> None:
        company = _company(db_session, category_slug="restaurante", region_name="São Paulo")
        _audited(db_session, company, site_state=DataState.NOT_DETECTED, opportunity_score=75.0, tier=OpportunityTier.MEDIUM_HIGH)

        page = list_companies(db_session)

        item = page.items[0]
        assert item.has_audit is True
        assert item.site_state == DataState.NOT_DETECTED
        assert item.opportunity_score == 75.0
        assert item.opportunity_tier == OpportunityTier.MEDIUM_HIGH
        assert item.category_slug == "restaurante"
        assert item.region_name == "São Paulo"

    def test_filter_by_tier(self, db_session: Session) -> None:
        high = _company(db_session, name="Alta")
        _audited(db_session, high, site_state=DataState.NOT_DETECTED, opportunity_score=90.0, tier=OpportunityTier.HIGH)
        low = _company(db_session, name="Baixa")
        _audited(db_session, low, site_state=DataState.CONFIRMED, opportunity_score=10.0, tier=OpportunityTier.VERY_LOW)

        page = list_companies(db_session, tier=OpportunityTier.HIGH)

        assert page.total == 1
        assert page.items[0].canonical_name == "Alta"

    def test_filter_by_score_range(self, db_session: Session) -> None:
        for name, score in [("A", 20.0), ("B", 50.0), ("C", 90.0)]:
            company = _company(db_session, name=name)
            _audited(db_session, company, site_state=DataState.NOT_DETECTED, opportunity_score=score)

        page = list_companies(db_session, min_score=40.0, max_score=80.0)

        assert page.total == 1
        assert page.items[0].canonical_name == "B"

    def test_filter_by_site_state(self, db_session: Session) -> None:
        confirmed = _company(db_session, name="Tem site")
        _audited(db_session, confirmed, site_state=DataState.CONFIRMED)
        none_found = _company(db_session, name="Sem site")
        _audited(db_session, none_found, site_state=DataState.NOT_DETECTED)

        page = list_companies(db_session, site_state=DataState.NOT_DETECTED)

        assert page.total == 1
        assert page.items[0].canonical_name == "Sem site"

    def test_filter_by_category_and_region(self, db_session: Session) -> None:
        _company(db_session, name="Certa", category_slug="barbearia", region_name="Recife")
        _company(db_session, name="Errada", category_slug="dentista", region_name="Salvador")

        page = list_companies(db_session, category_slug="barbearia")
        assert page.total == 1
        assert page.items[0].canonical_name == "Certa"

        page = list_companies(db_session, region_name="Salvador")
        assert page.total == 1
        assert page.items[0].canonical_name == "Errada"

    def test_filter_by_audited_flag(self, db_session: Session) -> None:
        audited_co = _company(db_session, name="Auditada")
        _audited(db_session, audited_co, site_state=DataState.CONFIRMED)
        _company(db_session, name="Não auditada")

        page = list_companies(db_session, audited=True)
        assert page.total == 1
        assert page.items[0].canonical_name == "Auditada"

        page = list_companies(db_session, audited=False)
        assert page.total == 1
        assert page.items[0].canonical_name == "Não auditada"

    def test_filter_by_name_search(self, db_session: Session) -> None:
        _company(db_session, name="Padaria do João")
        _company(db_session, name="Barbearia do Zé")

        page = list_companies(db_session, q="padaria")

        assert page.total == 1
        assert page.items[0].canonical_name == "Padaria do João"

    def test_pagination_limit_and_offset(self, db_session: Session) -> None:
        for i in range(5):
            _company(db_session, name=f"Empresa {i}")

        page = list_companies(db_session, limit=2, offset=2)

        assert page.total == 5
        assert len(page.items) == 2
        assert page.limit == 2
        assert page.offset == 2

    def test_sort_by_opportunity_score_desc_with_nulls_last(self, db_session: Session) -> None:
        no_score = _company(db_session, name="Sem score")
        low = _company(db_session, name="Baixa")
        _audited(db_session, low, site_state=DataState.CONFIRMED, opportunity_score=20.0)
        high = _company(db_session, name="Alta")
        _audited(db_session, high, site_state=DataState.NOT_DETECTED, opportunity_score=95.0)

        page = list_companies(db_session, sort_by="opportunity_score")

        names = [item.canonical_name for item in page.items]
        assert names == ["Alta", "Baixa", "Sem score"]

    def test_latest_audit_is_used_not_an_older_one(self, db_session: Session) -> None:
        company = _company(db_session)
        _audited(db_session, company, site_state=DataState.NOT_DETECTED, opportunity_score=30.0)
        _audited(db_session, company, site_state=DataState.CONFIRMED, opportunity_score=80.0)

        page = list_companies(db_session)

        assert page.total == 1
        assert page.items[0].site_state == DataState.CONFIRMED
        assert page.items[0].opportunity_score == 80.0


class TestGetDashboardStats:
    def test_empty_database(self, db_session: Session) -> None:
        stats = get_dashboard_stats(db_session)
        assert stats.total_companies == 0
        assert stats.audited_companies == 0
        assert stats.high_opportunity_companies == 0
        assert stats.average_opportunity_score is None

    def test_counts_reflect_real_data(self, db_session: Session) -> None:
        not_audited = _company(db_session, name="Não auditada")
        high = _company(db_session, name="Alta")
        _audited(db_session, high, site_state=DataState.NOT_DETECTED, opportunity_score=90.0, tier=OpportunityTier.HIGH)
        low = _company(db_session, name="Baixa")
        _audited(db_session, low, site_state=DataState.CONFIRMED, opportunity_score=10.0, tier=OpportunityTier.VERY_LOW)

        stats = get_dashboard_stats(db_session)

        assert stats.total_companies == 3
        assert stats.audited_companies == 2
        assert stats.high_opportunity_companies == 1
        assert stats.average_opportunity_score == 50.0

    def test_average_uses_latest_score_not_older_ones(self, db_session: Session) -> None:
        company = _company(db_session)
        _audited(db_session, company, site_state=DataState.NOT_DETECTED, opportunity_score=10.0)
        _audited(db_session, company, site_state=DataState.CONFIRMED, opportunity_score=90.0)

        stats = get_dashboard_stats(db_session)

        assert stats.average_opportunity_score == 90.0


class TestGetCompanyDetail:
    def test_unknown_company_returns_none(self, db_session: Session) -> None:
        assert get_company_detail(db_session, uuid.uuid4()) is None

    def test_company_without_audit_has_no_latest_audit_or_score(self, db_session: Session) -> None:
        company = _company(db_session)

        detail = get_company_detail(db_session, company.id)

        assert detail is not None
        assert detail.latest_audit is None
        assert detail.latest_score is None
        assert detail.latest_brief is None
        assert detail.evidence == []
        assert detail.sources == []

    def test_full_detail_aggregates_everything(self, db_session: Session) -> None:
        company = _company(db_session, category_slug="restaurante", region_name="Recife")
        db_session.add(
            CompanySource(
                company_id=company.id, source="google_places", external_id="place-1",
                confidence=ConfidenceLevel.HIGH,
            )
        )
        db_session.add(
            Evidence(
                company_id=company.id, field="phone", value="+5511987654321", state=DataState.CONFIRMED,
                source="google_places", method=EvidenceMethod.STRUCTURED_FIELD, confidence=ConfidenceLevel.HIGH,
            )
        )
        db_session.flush()
        snapshot = _audited(db_session, company, site_state=DataState.NOT_DETECTED, opportunity_score=65.0, tier=OpportunityTier.MEDIUM_HIGH)
        score = db_session.query(OpportunityScore).filter(OpportunityScore.audit_snapshot_id == snapshot.id).one()
        db_session.add(
            SalesBrief(
                company_id=company.id, opportunity_score_id=score.id, status=SalesBriefStatus.COMPLETED,
                content={"summary": "ok"}, provider="fake", prompt_version="v1",
            )
        )
        db_session.flush()

        detail = get_company_detail(db_session, company.id)

        assert detail is not None
        assert detail.company.canonical_name == company.canonical_name
        assert len(detail.sources) == 1
        assert len(detail.evidence) == 1
        assert detail.latest_audit is not None and detail.latest_audit.id == snapshot.id
        assert detail.latest_score is not None and detail.latest_score.score == 65.0
        assert detail.latest_brief is not None and detail.latest_brief.content == {"summary": "ok"}

    def test_superseded_evidence_is_excluded(self, db_session: Session) -> None:
        company = _company(db_session)
        old = Evidence(
            company_id=company.id, field="phone", value="+5511900000000", state=DataState.CONFIRMED,
            source="google_places", method=EvidenceMethod.STRUCTURED_FIELD, confidence=ConfidenceLevel.HIGH,
        )
        db_session.add(old)
        db_session.flush()
        new = Evidence(
            company_id=company.id, field="phone", value="+5511987654321", state=DataState.CONFIRMED,
            source="google_places", method=EvidenceMethod.STRUCTURED_FIELD, confidence=ConfidenceLevel.HIGH,
        )
        db_session.add(new)
        db_session.flush()
        old.mark_superseded_by(new)
        db_session.flush()

        detail = get_company_detail(db_session, company.id)

        assert detail is not None
        assert len(detail.evidence) == 1
        assert detail.evidence[0].value == "+5511987654321"
