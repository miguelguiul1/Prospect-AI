from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.domains.companies.models import Company
from app.domains.discovery.dto import DiscoveredCompany
from app.domains.evidence.enums import ConfidenceLevel, DataState, EvidenceMethod
from app.domains.evidence.models import Evidence
from app.domains.identity.models import CompanySource
from app.domains.identity.profile import build_profile_from_company, build_profile_from_discovered


def test_build_profile_from_discovered_normalizes_fields() -> None:
    discovered = DiscoveredCompany(
        source="google_places",
        external_id="ChIJ_x",
        name="  Restaurante   São João  ",
        formatted_address="Rua X,  100",
        phone="(11) 98765-4321",
        website="EMPRESA.com.br/",
        category="italian_restaurant",
    )

    profile = build_profile_from_discovered(discovered, region_id=None)

    assert profile.name == "Restaurante São João"
    assert profile.phone == "+5511987654321"
    assert profile.website == "https://empresa.com.br"
    assert profile.category == "italian restaurant"


def test_build_profile_from_discovered_never_invents_missing_fields() -> None:
    discovered = DiscoveredCompany(source="google_places", external_id="ChIJ_bare")

    profile = build_profile_from_discovered(discovered, region_id=None)

    assert profile.name is None
    assert profile.phone is None
    assert profile.website is None


class TestBuildProfileFromCompany:
    def test_reads_current_evidence_values(self, db_session: Session) -> None:
        company = Company(canonical_name="Barbearia Teste")
        db_session.add(company)
        db_session.flush()

        db_session.add_all(
            [
                Evidence(
                    company_id=company.id, field="phone", value="+5511987654321",
                    state=DataState.CONFIRMED, source="google_places",
                    method=EvidenceMethod.STRUCTURED_FIELD, confidence=ConfidenceLevel.HIGH,
                ),
                Evidence(
                    company_id=company.id, field="website", value="https://barbearia.example.com",
                    state=DataState.CONFIRMED, source="google_places",
                    method=EvidenceMethod.STRUCTURED_FIELD, confidence=ConfidenceLevel.HIGH,
                ),
            ]
        )
        db_session.flush()

        profile = build_profile_from_company(db_session, company)

        assert profile.name == "Barbearia Teste"
        assert profile.phone == "+5511987654321"
        assert profile.website == "https://barbearia.example.com"

    def test_ignores_superseded_evidence(self, db_session: Session) -> None:
        company = Company(canonical_name="Barbearia Teste")
        db_session.add(company)
        db_session.flush()

        old = Evidence(
            company_id=company.id, field="phone", value="+5511911111111",
            state=DataState.CONFIRMED, source="google_places",
            method=EvidenceMethod.STRUCTURED_FIELD, confidence=ConfidenceLevel.HIGH,
        )
        db_session.add(old)
        db_session.flush()

        new = Evidence(
            company_id=company.id, field="phone", value="+5511922222222",
            state=DataState.CONFIRMED, source="google_places",
            method=EvidenceMethod.STRUCTURED_FIELD, confidence=ConfidenceLevel.HIGH,
        )
        db_session.add(new)
        db_session.flush()
        old.mark_superseded_by(new)
        db_session.flush()

        profile = build_profile_from_company(db_session, company)

        assert profile.phone == "+5511922222222"

    def test_uses_coordinates_from_most_recently_seen_source(self, db_session: Session) -> None:
        company = Company(canonical_name="Barbearia Teste")
        db_session.add(company)
        db_session.flush()

        older = CompanySource(
            company_id=company.id, source="openstreetmap", external_id="node/1",
            confidence=ConfidenceLevel.MEDIUM, latitude=-23.0, longitude=-46.0,
        )
        db_session.add(older)
        db_session.flush()

        newer = CompanySource(
            company_id=company.id, source="google_places", external_id="ChIJ_1",
            confidence=ConfidenceLevel.HIGH, latitude=-23.5505, longitude=-46.6333,
        )
        db_session.add(newer)
        db_session.flush()

        profile = build_profile_from_company(db_session, company)

        assert profile.latitude == -23.5505
        assert profile.longitude == -46.6333

    def test_no_coordinates_when_no_source_reported_any(self, db_session: Session) -> None:
        company = Company(canonical_name="Barbearia Sem Coordenadas")
        db_session.add(company)
        db_session.flush()

        profile = build_profile_from_company(db_session, company)

        assert profile.latitude is None
        assert profile.longitude is None
