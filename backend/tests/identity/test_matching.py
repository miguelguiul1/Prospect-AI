"""Testes do motor de comparação puro (`resolve()`), casos B a I do prompt
da Fase 2. O caso A (mesmo `source`+`external_id`) não passa por aqui — é
resolvido antes de chegar ao Identity Resolution, por
`app.domains.discovery.persistence.find_or_create_company` (ver
tests/discovery/test_service.py::TestReprocessingIsAppendOnly).

Nenhum destes testes toca o banco — `CompanyProfile` é construído à mão.
"""
from __future__ import annotations

import uuid

import pytest

from app.core.config import Settings
from app.domains.identity.enums import MatchDecision
from app.domains.identity.matching import is_trusted_website, resolve
from app.domains.identity.profile import CompanyProfile


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        identity_name_similarity_threshold=75,
        identity_address_similarity_threshold=85,
        identity_geo_proximity_meters=150.0,
    )


def _profile(
    *,
    label: str = "test",
    name: str | None = None,
    phone: str | None = None,
    address: str | None = None,
    website: str | None = None,
    category: str | None = None,
    region_id: uuid.UUID | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
) -> CompanyProfile:
    return CompanyProfile(
        label=label, name=name, phone=phone, address=address, website=website,
        category=category, region_id=region_id, latitude=latitude, longitude=longitude,
    )


SETTINGS = _settings()


class TestCaseB_SameCompanyFormattedDifferently:
    def test_match_when_phone_matches_and_name_is_compatible(self) -> None:
        candidate = _profile(name="REST. SAO JOAO", phone="+5511987654321")
        existing = _profile(name="Restaurante São João", phone="+5511987654321")

        result = resolve(candidate, existing, settings=SETTINGS)

        assert result.decision == MatchDecision.MATCH
        assert "telefone igual" in " ".join(result.reasons) or any("telefone" in r for r in result.reasons)


class TestCaseC_SameNameDifferentCity:
    def test_no_match_when_region_conflicts_even_with_identical_name(self) -> None:
        region_sp = uuid.uuid4()
        region_campinas = uuid.uuid4()
        candidate = _profile(name="Restaurante Central", region_id=region_campinas)
        existing = _profile(name="Restaurante Central", region_id=region_sp)

        result = resolve(candidate, existing, settings=SETTINGS)

        assert result.decision == MatchDecision.NO_MATCH
        assert result.signals["region_conflict"] is True


class TestCaseD_SimilarNamesDifferentPhones:
    def test_no_match_when_phones_conflict_despite_similar_names(self) -> None:
        candidate = _profile(name="Restaurante do Joao", phone="+5511911111111")
        existing = _profile(name="Restaurante do João", phone="+5511922222222")

        result = resolve(candidate, existing, settings=SETTINGS)

        assert result.decision == MatchDecision.NO_MATCH
        assert result.signals["phone_conflict"] is True


class TestCaseE_TrivialAddressFormatting:
    def test_match_when_phone_and_address_are_compatible(self) -> None:
        candidate = _profile(name="Restaurante São João", phone="+5511987654321", address="Rua X 100")
        existing = _profile(name="Restaurante São João", phone="+5511987654321", address="Rua X, 100")

        result = resolve(candidate, existing, settings=SETTINGS)

        assert result.decision == MatchDecision.MATCH


class TestCaseF_NearbyCompaniesNoOtherSignal:
    def test_inconclusive_when_only_geographic_proximity(self) -> None:
        candidate = _profile(latitude=-23.5505, longitude=-46.6333)
        existing = _profile(latitude=-23.5506, longitude=-46.6333)  # ~11m de distância

        result = resolve(candidate, existing, settings=SETTINGS)

        assert result.decision == MatchDecision.INCONCLUSIVE
        assert result.signals["distance_m"] < SETTINGS.identity_geo_proximity_meters

    def test_no_match_when_far_apart(self) -> None:
        candidate = _profile(latitude=-23.5505, longitude=-46.6333)
        existing = _profile(latitude=-22.9519, longitude=-43.2105)  # São Paulo vs Rio

        result = resolve(candidate, existing, settings=SETTINGS)

        assert result.decision == MatchDecision.NO_MATCH


class TestCaseG_SamePhoneDifferentNames:
    def test_inconclusive_never_auto_matches_on_phone_alone(self) -> None:
        candidate = _profile(name="Padaria Estrela", phone="+5511987654321")
        existing = _profile(name="Restaurante do João", phone="+5511987654321")

        result = resolve(candidate, existing, settings=SETTINGS)

        assert result.decision == MatchDecision.INCONCLUSIVE
        assert result.signals["phone_match"] is True


class TestCaseH_SameOfficialWebsite:
    def test_match_when_official_website_matches_and_name_compatible(self) -> None:
        candidate = _profile(name="Restaurante do Joao", website="https://restaurantedojoao.com.br")
        existing = _profile(name="restaurante do joao", website="https://restaurantedojoao.com.br")

        result = resolve(candidate, existing, settings=SETTINGS)

        assert result.decision == MatchDecision.MATCH
        assert result.confidence.value == "high"


class TestCaseI_SocialMediaIsNeverAnOfficialWebsite:
    def test_instagram_url_never_counts_as_official_website_match(self) -> None:
        assert is_trusted_website("https://instagram.com/restaurantedojoao") is False

    def test_same_instagram_url_alone_does_not_match(self) -> None:
        candidate = _profile(name="Padaria Estrela", website="https://instagram.com/restaurantedojoao")
        existing = _profile(name="Restaurante do João", website="https://instagram.com/restaurantedojoao")

        result = resolve(candidate, existing, settings=SETTINGS)

        assert result.decision != MatchDecision.MATCH

    def test_same_instagram_url_with_compatible_name_is_inconclusive_not_match(self) -> None:
        """Mesmo com nome compatível, um Instagram compartilhado não deve
        contar como o sinal forte (site oficial) exigido para MATCH."""
        candidate = _profile(name="Restaurante do Joao", website="https://instagram.com/restaurantedojoao")
        existing = _profile(name="restaurante do joao", website="https://instagram.com/restaurantedojoao")

        result = resolve(candidate, existing, settings=SETTINGS)

        assert result.decision == MatchDecision.INCONCLUSIVE


class TestNoSignalsAtAll:
    def test_no_match_when_nothing_is_comparable(self) -> None:
        candidate = _profile(name="Empresa X")
        existing = _profile(name="Empresa Y")

        result = resolve(candidate, existing, settings=SETTINGS)

        assert result.decision == MatchDecision.NO_MATCH


class TestReasonsAreExplainable:
    def test_match_result_always_has_at_least_one_reason(self) -> None:
        candidate = _profile(name="Restaurante São João", phone="+5511987654321")
        existing = _profile(name="Restaurante São João", phone="+5511987654321")

        result = resolve(candidate, existing, settings=SETTINGS)

        assert len(result.reasons) >= 1
        assert all(isinstance(r, str) and r for r in result.reasons)
