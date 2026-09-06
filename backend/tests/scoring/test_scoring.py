"""Testes puros da fórmula do Opportunity Score (`app.domains.scoring.scoring`).

Nenhum banco, nenhuma rede — `compute_opportunity_score` é uma função pura;
os testes aqui constroem `ScoringContext` diretamente, como a Fase 4 pede
("função pura: os mesmos dados sempre produzem o mesmo resultado").
"""
from __future__ import annotations

import uuid

from app.domains.audit.models import WebsiteQuality
from app.domains.evidence.enums import ConfidenceLevel, DataState
from app.domains.scoring.scoring import (
    WEIGHTS,
    EvidenceRef,
    ScoringContext,
    classify,
    compute_opportunity_score,
)


def _quality(score: float | None) -> WebsiteQuality | None:
    if score is None:
        return None
    quality = WebsiteQuality(audit_snapshot_id=uuid.uuid4(), score=score)
    quality.id = uuid.uuid4()
    return quality


def _ref(field: str, value: str | None) -> EvidenceRef | None:
    if value is None:
        return None
    return EvidenceRef(field=field, value=value, evidence_id=str(uuid.uuid4()))


def _context(
    *,
    site_state: DataState = DataState.NOT_DETECTED,
    website_quality_score: float | None = None,
    website_value: str | None = None,
    category_slug: str | None = None,
    rating: str | None = None,
    review_count: str | None = None,
    phone: str | None = None,
    address: str | None = None,
    website_contact_available: str | None = None,
) -> ScoringContext:
    return ScoringContext(
        site_state=site_state,
        website_quality=_quality(website_quality_score),
        website_value=_ref("website", website_value),
        category_slug=category_slug,
        rating=_ref("rating", rating),
        review_count=_ref("review_count", review_count),
        phone=_ref("phone", phone),
        address=_ref("address", address),
        website_contact_available=_ref("website_contact_available", website_contact_available),
    )


class TestBoundsAndDeterminism:
    def test_weights_sum_to_one(self) -> None:
        assert round(sum(WEIGHTS.values()), 6) == 1.0

    def test_score_never_below_zero_or_above_hundred(self) -> None:
        for ctx in [
            _context(site_state=DataState.NOT_DETECTED, rating="5", review_count="10000"),
            _context(site_state=DataState.CONFIRMED, website_quality_score=100.0),
        ]:
            result = compute_opportunity_score(ctx)
            assert result.score is not None
            assert 0.0 <= result.score <= 100.0

    def test_same_context_produces_same_result(self) -> None:
        ctx = _context(site_state=DataState.NOT_DETECTED, rating="4.5", review_count="30", phone="+551199999999")
        first = compute_opportunity_score(ctx)
        second = compute_opportunity_score(ctx)
        assert first.score == second.score
        assert first.tier == second.tier
        assert first.confidence == second.confidence
        assert first.breakdown == second.breakdown

    def test_classify_boundaries(self) -> None:
        assert classify(100.0) == "high"
        assert classify(80.0) == "high"
        assert classify(79.9) == "medium_high"
        assert classify(60.0) == "medium_high"
        assert classify(59.9) == "medium"
        assert classify(40.0) == "medium"
        assert classify(39.9) == "low"
        assert classify(20.0) == "low"
        assert classify(19.9) == "very_low"
        assert classify(0.0) == "very_low"


class TestCasosImportantes:
    """Espelha os "casos importantes" do Prompt 07 (Fase 4)."""

    def test_no_confirmed_site_with_strong_signals_scores_high(self) -> None:
        ctx = _context(
            site_state=DataState.NOT_DETECTED,
            category_slug="restaurante",
            rating="4.7",
            review_count="120",
            phone="+5511987654321",
            address="Rua Exemplo, 123",
        )
        result = compute_opportunity_score(ctx)
        assert result.score is not None
        assert result.score >= 60.0
        assert result.tier in ("high", "medium_high")

    def test_excellent_site_and_good_presence_scores_lower_than_no_site_case(self) -> None:
        no_site = compute_opportunity_score(
            _context(site_state=DataState.NOT_DETECTED, category_slug="restaurante", rating="4.7", review_count="120", phone="+5511987654321", address="Rua Exemplo, 123")
        )
        excellent_site = compute_opportunity_score(
            _context(
                site_state=DataState.CONFIRMED,
                website_quality_score=95.0,
                website_value="https://empresa.com.br",
                category_slug="restaurante",
                rating="4.7",
                review_count="120",
                phone="+5511987654321",
                address="Rua Exemplo, 123",
                website_contact_available="true",
            )
        )
        assert excellent_site.score is not None and no_site.score is not None
        assert excellent_site.score < no_site.score
        assert excellent_site.tier in ("low", "very_low", "medium")

    def test_bad_site_with_good_visibility_is_still_relevant_opportunity(self) -> None:
        excellent_site = compute_opportunity_score(
            _context(
                site_state=DataState.CONFIRMED, website_quality_score=95.0, website_value="https://empresa.com.br",
                category_slug="restaurante", rating="4.7", review_count="120", phone="+5511987654321",
                address="Rua Exemplo, 123", website_contact_available="true",
            )
        )
        bad_site = compute_opportunity_score(
            _context(
                site_state=DataState.CONFIRMED, website_quality_score=25.0, website_value="https://empresa.com.br",
                category_slug="restaurante", rating="4.7", review_count="120", phone="+5511987654321",
                address="Rua Exemplo, 123", website_contact_available="true",
            )
        )
        assert bad_site.score is not None and excellent_site.score is not None
        # Site ruim é MAIS oportunidade que site excelente, mas nunca 0 —
        # visibilidade/contactabilidade ainda contam.
        assert bad_site.score > excellent_site.score
        assert bad_site.score > 0.0

    def test_insufficient_evidence_yields_low_confidence(self) -> None:
        result = compute_opportunity_score(_context(site_state=DataState.NOT_CHECKED))
        assert result.confidence == ConfidenceLevel.LOW
        assert result.score is not None
        # Conservador: nem no piso nem no teto, já que só 2 das 6 dimensões
        # tinham dado (website_gap e contactability são sempre calculadas).
        assert 0.0 < result.score < 60.0

    def test_high_reviews_are_capped_and_never_dominate(self) -> None:
        moderate = compute_opportunity_score(_context(site_state=DataState.NOT_DETECTED, rating="5.0", review_count="50"))
        huge = compute_opportunity_score(_context(site_state=DataState.NOT_DETECTED, rating="5.0", review_count="50000"))
        # Saturação: 50 avaliações já satura o componente de reviews —
        # 50.000 avaliações não deveria mudar o score (nunca vira proxy de
        # "quanto maior, mais dinheiro").
        assert moderate.score == huge.score

    def test_inconclusive_site_state_never_becomes_confirmed_or_not_detected(self) -> None:
        result = compute_opportunity_score(_context(site_state=DataState.INCONCLUSIVE))
        dims = result.breakdown["dimensions"]
        # Nem 0 (que significaria "site existe") nem 100 (que significaria
        # "site não existe") — um valor intermediário explícito.
        assert dims["website_gap"]["raw"] == 50.0
        assert result.confidence == ConfidenceLevel.LOW

    def test_opportunity_score_is_never_a_copy_of_website_quality_score(self) -> None:
        # Site com Website Quality Score = 100 (o melhor possível) ainda assim
        # produz um Opportunity Score BEM abaixo de 100 — não é o mesmo número,
        # nem uma transformação linear trivial dele.
        result = compute_opportunity_score(
            _context(site_state=DataState.CONFIRMED, website_quality_score=100.0, website_value="https://empresa.com.br")
        )
        assert result.score is not None
        assert result.score != 100.0


class TestDimensoesIndividuais:
    def test_digital_presence_gap_flags_social_only_presence(self) -> None:
        result = compute_opportunity_score(_context(site_state=DataState.NOT_DETECTED, website_value="https://instagram.com/empresa"))
        dims = result.breakdown["dimensions"]
        assert dims["digital_presence_gap"]["raw"] == 90.0

    def test_digital_presence_gap_excluded_without_any_website_evidence(self) -> None:
        result = compute_opportunity_score(_context(site_state=DataState.NOT_DETECTED, website_value=None))
        dims = result.breakdown["dimensions"]
        assert dims["digital_presence_gap"]["raw"] is None
        assert dims["digital_presence_gap"]["contribution"] is None

    def test_segment_fit_uses_default_for_unmapped_category(self) -> None:
        result = compute_opportunity_score(_context(site_state=DataState.NOT_DETECTED, category_slug="categoria-inexistente"))
        dims = result.breakdown["dimensions"]
        assert dims["segment_fit"]["raw"] == 50.0
        assert "padrão" in dims["segment_fit"]["reason"] or "neutro" in dims["segment_fit"]["reason"]

    def test_segment_fit_excluded_without_category(self) -> None:
        result = compute_opportunity_score(_context(site_state=DataState.NOT_DETECTED, category_slug=None))
        dims = result.breakdown["dimensions"]
        assert dims["segment_fit"]["raw"] is None

    def test_contactability_accumulates_signals(self) -> None:
        none_known = compute_opportunity_score(_context(site_state=DataState.NOT_DETECTED))
        all_known = compute_opportunity_score(
            _context(site_state=DataState.NOT_DETECTED, phone="+5511987654321", address="Rua X, 1", website_contact_available="true")
        )
        dims_none = none_known.breakdown["dimensions"]
        dims_all = all_known.breakdown["dimensions"]
        assert dims_none["contactability"]["raw"] == 0.0
        assert dims_all["contactability"]["raw"] == 100.0

    def test_business_visibility_excluded_without_rating_or_reviews(self) -> None:
        result = compute_opportunity_score(_context(site_state=DataState.NOT_DETECTED))
        dims = result.breakdown["dimensions"]
        assert dims["business_visibility"]["raw"] is None
