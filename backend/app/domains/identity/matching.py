"""Motor de comparação de identidade: decide se dois `CompanyProfile`
representam a mesma empresa.

Regra central (arquitetura Fase 2, seção 9): é preferível manter duas
empresas separadas do que uni-las incorretamente. Por isso:

- `MATCH` só ocorre quando um sinal FORTE (telefone igual, ou site oficial
  igual) aparece COMBINADO com um segundo sinal compatível (nome ou
  endereço). Nenhum sinal isolado — nem telefone igual sozinho, nem nome
  idêntico sozinho, nem proximidade geográfica sozinha — é suficiente.
- Contradições concretas (telefones diferentes quando ambos são
  conhecidos; regiões diferentes quando ambas são conhecidas) resultam em
  `NO_MATCH` direto, mesmo com nomes muito parecidos.
- Tudo o que sobra — sinais parciais, corroboração fraca, informação
  insuficiente — vira `INCONCLUSIVE`, nunca um merge automático.

Este módulo não faz nenhuma consulta ao banco — é puro e determinístico,
por isso testável diretamente com `CompanyProfile`s construídos à mão (ver
tests/identity/test_matching.py, casos B a I do prompt da Fase 2).
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field

from rapidfuzz import fuzz

from app.core.config import Settings, get_settings
from app.domains.discovery.normalization import (  # noqa: F401 - reexportado para compatibilidade
    UNTRUSTED_WEBSITE_DOMAINS,
    is_trusted_website,
)
from app.domains.evidence.enums import ConfidenceLevel
from app.domains.identity.enums import MatchDecision
from app.domains.identity.geo import haversine_distance_meters
from app.domains.identity.profile import CompanyProfile

# `UNTRUSTED_WEBSITE_DOMAINS`/`is_trusted_website` viviam aqui até a Fase 3,
# quando o Digital Audit passou a precisar exatamente da mesma regra
# (distinguir site próprio de rede social/agregador). Promovidos para
# `app.domains.discovery.normalization` — reexportados aqui só para não
# quebrar quem já importa daqui (ex.: testes da Fase 2).


@dataclass(frozen=True)
class MatchResult:
    decision: MatchDecision
    confidence: ConfidenceLevel
    reasons: list[str] = field(default_factory=list)
    signals: dict = field(default_factory=dict)


def _fold(value: str) -> str:
    """Dobra maiúsculas/minúsculas e remove acentos só para efeito de
    comparação — nunca muda o valor exibido/armazenado (esse continua
    normalizado apenas via `app.domains.discovery.normalization`).
    RapidFuzz não faz esse dobramento sozinho: "São João" vs "SAO JOAO"
    pontua muito mais baixo sem isso do que a diferença real justificaria.
    """
    decomposed = unicodedata.normalize("NFKD", value)
    without_marks = "".join(c for c in decomposed if not unicodedata.combining(c))
    return without_marks.lower()


def _name_similarity(a: str | None, b: str | None) -> float | None:
    if not a or not b:
        return None
    return fuzz.token_sort_ratio(_fold(a), _fold(b))


def _address_similarity(a: str | None, b: str | None) -> float | None:
    if not a or not b:
        return None
    return fuzz.token_sort_ratio(_fold(a), _fold(b))


def _geo_distance(a: CompanyProfile, b: CompanyProfile) -> float | None:
    if a.latitude is None or a.longitude is None or b.latitude is None or b.longitude is None:
        return None
    return haversine_distance_meters(a.latitude, a.longitude, b.latitude, b.longitude)


def resolve(
    candidate: CompanyProfile,
    existing: CompanyProfile,
    *,
    settings: Settings | None = None,
) -> MatchResult:
    """Compara um candidato contra uma `Company` já conhecida.

    Não decide nada sobre persistência — apenas retorna a decisão e as
    razões. Quem decide o que fazer com o resultado é
    `IdentityResolutionService` (app.domains.identity.service).
    """
    settings = settings or get_settings()

    phone_match = candidate.phone is not None and candidate.phone == existing.phone
    phone_known_both = candidate.phone is not None and existing.phone is not None
    phone_conflict = phone_known_both and candidate.phone != existing.phone

    website_match_raw = candidate.website is not None and candidate.website == existing.website
    website_official_match = website_match_raw and is_trusted_website(candidate.website)

    name_score = _name_similarity(candidate.name, existing.name)
    name_compatible = name_score is not None and name_score >= settings.identity_name_similarity_threshold

    address_score = _address_similarity(candidate.address, existing.address)
    address_compatible = (
        address_score is not None and address_score >= settings.identity_address_similarity_threshold
    )

    region_known_both = candidate.region_id is not None and existing.region_id is not None
    region_conflict = region_known_both and candidate.region_id != existing.region_id

    category_match = (
        candidate.category is not None
        and existing.category is not None
        and candidate.category == existing.category
    )

    distance_m = _geo_distance(candidate, existing)
    geo_close = distance_m is not None and distance_m <= settings.identity_geo_proximity_meters

    signals = {
        "phone_match": phone_match,
        "phone_conflict": phone_conflict,
        "website_official_match": website_official_match,
        "name_score": name_score,
        "address_score": address_score,
        "region_conflict": region_conflict,
        "category_match": category_match,
        "distance_m": distance_m,
    }

    # --- 1. MATCH: sinal forte + segundo sinal compatível -------------------
    if phone_match and name_compatible:
        return MatchResult(
            MatchDecision.MATCH,
            ConfidenceLevel.HIGH,
            ["telefone igual", "nome compatível"],
            signals,
        )
    if website_official_match and name_compatible:
        return MatchResult(
            MatchDecision.MATCH,
            ConfidenceLevel.HIGH,
            ["site oficial igual", "nome compatível"],
            signals,
        )
    if phone_match and address_compatible:
        return MatchResult(
            MatchDecision.MATCH,
            ConfidenceLevel.HIGH,
            ["telefone igual", "endereço compatível"],
            signals,
        )

    # --- 2. NO_MATCH: contradição concreta ----------------------------------
    if phone_conflict and not website_official_match:
        return MatchResult(
            MatchDecision.NO_MATCH,
            ConfidenceLevel.HIGH,
            ["telefones diferentes e conhecidos em ambos os lados"],
            signals,
        )
    if region_conflict:
        return MatchResult(
            MatchDecision.NO_MATCH,
            ConfidenceLevel.MEDIUM,
            ["regiões diferentes e conhecidas em ambos os lados"],
            signals,
        )

    # --- 3. INCONCLUSIVE: sinal parcial, nunca decide sozinho ---------------
    if phone_match:
        return MatchResult(
            MatchDecision.INCONCLUSIVE,
            ConfidenceLevel.MEDIUM,
            ["telefone igual, mas nome/endereço não corroboram — requer revisão"],
            signals,
        )
    if website_match_raw and not website_official_match:
        return MatchResult(
            MatchDecision.INCONCLUSIVE,
            ConfidenceLevel.LOW,
            ["mesma URL, mas não é um domínio de site oficial (rede social/agregador)"],
            signals,
        )
    if name_compatible and (geo_close or category_match or address_compatible):
        return MatchResult(
            MatchDecision.INCONCLUSIVE,
            ConfidenceLevel.MEDIUM,
            ["nome compatível com corroboração parcial (categoria/proximidade/endereço)"],
            signals,
        )
    if geo_close:
        return MatchResult(
            MatchDecision.INCONCLUSIVE,
            ConfidenceLevel.LOW,
            ["localizações muito próximas, sem outro sinal — pode ser outra empresa no mesmo local"],
            signals,
        )

    # --- 4. Padrão seguro: nada sugere que sejam a mesma empresa ------------
    return MatchResult(
        MatchDecision.NO_MATCH,
        ConfidenceLevel.MEDIUM,
        ["nenhum sinal suficiente de identidade compartilhada"],
        signals,
    )
