from __future__ import annotations

from app.domains.audit.html_signals import HtmlSignals
from app.domains.audit.http_client import FetchResult
from app.domains.audit.scoring import compute_website_quality
from app.domains.evidence.enums import ConfidenceLevel, DataState


def _fetch(**overrides: object) -> FetchResult:
    defaults = dict(
        requested_url="https://empresa.example.com/",
        final_url="https://empresa.example.com/",
        status_code=200,
        headers={},
        content_type="text/html; charset=utf-8",
        body=b"<html></html>",
        truncated=False,
        elapsed_ms=200.0,
        redirect_chain=[],
    )
    defaults.update(overrides)
    return FetchResult(**defaults)


def _html(**overrides: object) -> HtmlSignals:
    signals = HtmlSignals()
    for key, value in overrides.items():
        setattr(signals, key, value)
    return signals


class TestNoScoreWhenNotAccessible:
    def test_score_is_none_when_site_not_confirmed(self) -> None:
        for state in (DataState.NOT_DETECTED, DataState.INCONCLUSIVE, DataState.INACCESSIBLE, DataState.NOT_CHECKED):
            result = compute_website_quality(site_state=state, fetch=None, html=None)
            assert result.score is None
            assert result.confidence is None
            assert result.limitations  # sempre explica por quê

    def test_inaccessibility_is_never_reported_as_a_bad_score(self) -> None:
        result = compute_website_quality(site_state=DataState.INACCESSIBLE, fetch=None, html=None)
        assert result.score is None  # nunca 0 — 0 implicaria "avaliamos e é ruim"


class TestDeterminismAndReproducibility:
    def test_same_inputs_always_produce_same_score(self) -> None:
        fetch = _fetch()
        html = _html(title="Empresa Exemplo Ltda", viewport_present=True, heading_count=1, h1_count=1)

        result_a = compute_website_quality(site_state=DataState.CONFIRMED, fetch=fetch, html=html)
        result_b = compute_website_quality(site_state=DataState.CONFIRMED, fetch=fetch, html=html)

        assert result_a.score == result_b.score
        assert result_a.components == result_b.components

    def test_score_is_between_0_and_100(self) -> None:
        fetch = _fetch()
        html = _html()
        result = compute_website_quality(site_state=DataState.CONFIRMED, fetch=fetch, html=html)
        assert 0.0 <= result.score <= 100.0


class TestSecurityDimension:
    def test_https_scores_full_security(self) -> None:
        fetch = _fetch(final_url="https://empresa.example.com/")
        result = compute_website_quality(site_state=DataState.CONFIRMED, fetch=fetch, html=_html())
        assert result.components["security"] == 100.0

    def test_http_scores_zero_security(self) -> None:
        fetch = _fetch(final_url="http://empresa.example.com/", requested_url="http://empresa.example.com/")
        result = compute_website_quality(site_state=DataState.CONFIRMED, fetch=fetch, html=_html())
        assert result.components["security"] == 0.0


class TestSeoDimension:
    def test_full_seo_signals_score_100(self) -> None:
        html = _html(
            title="Barbearia Exemplo - Cortes",  # 27 chars, dentro de 10-70
            meta_description="A" * 100,  # dentro de 50-160
            canonical="https://empresa.example.com/",
            language="pt-BR",
            robots_meta_blocking=False,
        )
        result = compute_website_quality(site_state=DataState.CONFIRMED, fetch=_fetch(), html=html)
        assert result.components["seo"] == 100.0

    def test_missing_seo_signals_score_zero(self) -> None:
        result = compute_website_quality(site_state=DataState.CONFIRMED, fetch=_fetch(), html=_html())
        assert result.components["seo"] == 10.0  # só o ponto de "não bloqueado por robots"

    def test_title_present_but_bad_length_scores_partial_credit(self) -> None:
        html = _html(title="X")  # 1 char, fora do intervalo ideal
        result = compute_website_quality(site_state=DataState.CONFIRMED, fetch=_fetch(), html=html)
        # 15 (titulo presente, tamanho ruim) + 10 (nao bloqueado por robots)
        assert result.components["seo"] == 25.0


class TestContentDimension:
    def test_all_content_signals_score_100(self) -> None:
        html = _html(heading_count=2, h1_count=1, phone_like_text_found=True, social_links=["https://instagram.com/x"])
        result = compute_website_quality(site_state=DataState.CONFIRMED, fetch=_fetch(), html=html)
        assert result.components["content"] == 100.0

    def test_no_content_signals_score_zero(self) -> None:
        result = compute_website_quality(site_state=DataState.CONFIRMED, fetch=_fetch(), html=_html())
        assert result.components["content"] == 0.0


class TestUxDimension:
    def test_viewport_present_scores_50(self) -> None:
        html = _html(viewport_present=True)
        result = compute_website_quality(site_state=DataState.CONFIRMED, fetch=_fetch(), html=html)
        assert result.components["ux"] == 50.0

    def test_all_ux_signals_score_100(self) -> None:
        html = _html(viewport_present=True, internal_link_count=5, form_present=True)
        result = compute_website_quality(site_state=DataState.CONFIRMED, fetch=_fetch(), html=html)
        assert result.components["ux"] == 100.0


class TestTechnicalDimension:
    def test_fast_html_not_truncated_scores_100(self) -> None:
        fetch = _fetch(elapsed_ms=500.0, content_type="text/html", truncated=False)
        result = compute_website_quality(site_state=DataState.CONFIRMED, fetch=fetch, html=_html())
        assert result.components["technical"] == 100.0

    def test_slow_response_scores_lower_but_not_zero(self) -> None:
        fetch = _fetch(elapsed_ms=5000.0)
        result = compute_website_quality(site_state=DataState.CONFIRMED, fetch=fetch, html=_html())
        assert result.components["technical"] == 60.0  # 10 (lento) + 30 (html) + 20 (nao truncado)
        assert result.components["technical"] > 0  # lento nunca zera a dimensao

    def test_truncated_response_loses_points(self) -> None:
        fetch = _fetch(truncated=True)
        result = compute_website_quality(site_state=DataState.CONFIRMED, fetch=fetch, html=_html())
        assert result.components["technical"] == 80.0  # 50 (rapido) + 30 (html) + 0 (truncado)


class TestNonHtmlContent:
    def test_non_html_content_type_zeroes_content_dimensions_but_keeps_security(self) -> None:
        fetch = _fetch(content_type="application/pdf")
        result = compute_website_quality(site_state=DataState.CONFIRMED, fetch=fetch, html=None)

        assert result.components["security"] == 100.0  # https é independente do content-type
        assert result.components["seo"] == 10.0  # não bloqueado por robots (default)
        assert any("não é HTML" in limitation for limitation in result.limitations)
        assert result.confidence == ConfidenceLevel.LOW


class TestConfidence:
    def test_clean_html_response_has_high_confidence(self) -> None:
        result = compute_website_quality(site_state=DataState.CONFIRMED, fetch=_fetch(), html=_html())
        assert result.confidence == ConfidenceLevel.HIGH

    def test_truncated_response_has_medium_confidence(self) -> None:
        fetch = _fetch(truncated=True)
        result = compute_website_quality(site_state=DataState.CONFIRMED, fetch=fetch, html=_html())
        assert result.confidence == ConfidenceLevel.MEDIUM

    def test_non_200_status_has_medium_confidence(self) -> None:
        fetch = _fetch(status_code=404)
        result = compute_website_quality(site_state=DataState.CONFIRMED, fetch=fetch, html=_html())
        assert result.confidence == ConfidenceLevel.MEDIUM


class TestLimitationsAreExplainable:
    def test_missing_images_is_noted_as_limitation(self) -> None:
        result = compute_website_quality(site_state=DataState.CONFIRMED, fetch=_fetch(), html=_html())
        assert any("imagens" in limitation for limitation in result.limitations)

    def test_non_200_status_is_noted_as_limitation(self) -> None:
        fetch = _fetch(status_code=500)
        result = compute_website_quality(site_state=DataState.CONFIRMED, fetch=fetch, html=_html())
        assert any("500" in limitation for limitation in result.limitations)
