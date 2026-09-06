"""Website Quality Score: metodologia determinística e reproduzível.

**O que este score NÃO é** (arquitetura Fase 3, seção 11): não é chance de
venda, não é potencial financeiro, não é prioridade comercial. É só uma
avaliação da qualidade técnica/presença do website — o Opportunity Score
(Fase 4, ainda não implementado) é quem vai combinar isso com outros
fatores para decidir prioridade comercial.

**Metodologia.** Cinco dimensões, cada uma 0-100, combinadas por média
ponderada:

| Dimensão | Peso | Por quê esse peso |
|---|---|---|
| Segurança | 25% | HTTPS é binário e crítico — um site sem ele expõe visitantes; pesa mais que qualquer sinal de conteúdo. |
| SEO técnico | 20% | Afeta diretamente se a empresa é encontrada organicamente. |
| Conteúdo | 20% | Estrutura + informação de contato é o mínimo para o site cumprir sua função comercial. |
| UX/Mobile | 20% | Maioria do tráfego de busca local é mobile; viewport/navegação/formulário importam tanto quanto SEO. |
| Aspectos técnicos | 15% | Menor peso de propósito: os sinais aqui (tempo de resposta de UMA requisição, content-type, truncamento) são os mais grosseiros — nunca fingimos ter rodado Lighthouse/Core Web Vitals. |

Os pesos são uma hipótese inicial documentada, não um resultado de dados
reais — no mesmo espírito dos limiares de similaridade da Fase 2
(`docs/identity-resolution.md`), que também aguardam recalibração futura.

**Reprodutibilidade.** `compute_website_quality` é uma função pura: os
mesmos `HtmlSignals`/`FetchResult` sempre produzem o mesmo score. Nenhuma
IA participa deste cálculo.

**Quando não há score.** Se o site não foi confirmado como acessível
(`site_state != DataState.CONFIRMED`), nenhum score é calculado —
`score=None` — porque não é possível avaliar a qualidade de algo que não
foi possível verificar. Isso nunca é reinterpretado como "site ruim" (nota
0); é reportado como "não avaliável", com o motivo em `limitations`.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.domains.audit.html_signals import HtmlSignals
from app.domains.audit.http_client import FetchResult
from app.domains.evidence.enums import ConfidenceLevel, DataState

_WEIGHTS = {
    "security": 0.25,
    "seo": 0.20,
    "content": 0.20,
    "ux": 0.20,
    "technical": 0.15,
}

_HTML_CONTENT_TYPES = ("text/html", "application/xhtml+xml")


@dataclass(frozen=True)
class WebsiteQualityResult:
    score: float | None
    components: dict[str, float]
    signals: dict
    confidence: ConfidenceLevel | None
    limitations: list[str] = field(default_factory=list)


def is_html_content_type(content_type: str | None) -> bool:
    if not content_type:
        return False
    return any(content_type.lower().startswith(ct) for ct in _HTML_CONTENT_TYPES)


def _score_security(fetch: FetchResult) -> float:
    return 100.0 if fetch.is_https else 0.0


def _score_seo(html: HtmlSignals) -> float:
    score = 0.0

    if html.title:
        score += 30.0 if 10 <= len(html.title) <= 70 else 15.0

    if html.meta_description:
        score += 30.0 if 50 <= len(html.meta_description) <= 160 else 15.0

    if html.canonical:
        score += 15.0
    if html.language:
        score += 15.0
    if not html.robots_meta_blocking:
        score += 10.0

    return min(score, 100.0)


def _score_content(html: HtmlSignals) -> float:
    score = 0.0

    if html.heading_count >= 1:
        score += 25.0
    if html.h1_count >= 1:
        score += 15.0
    if html.phone_like_text_found or html.contact_link_found:
        score += 35.0
    if html.social_links:
        score += 25.0

    return min(score, 100.0)


def _score_ux(html: HtmlSignals) -> float:
    score = 0.0

    if html.viewport_present:
        score += 50.0
    if html.internal_link_count >= 3:
        score += 30.0
    if html.form_present:
        score += 20.0

    return min(score, 100.0)


def _score_technical(fetch: FetchResult) -> float:
    score = 0.0

    if fetch.elapsed_ms < 1000:
        score += 50.0
    elif fetch.elapsed_ms < 3000:
        score += 30.0
    else:
        score += 10.0

    if is_html_content_type(fetch.content_type):
        score += 30.0
    if not fetch.truncated:
        score += 20.0

    return min(score, 100.0)


def compute_website_quality(
    *,
    site_state: DataState,
    fetch: FetchResult | None,
    html: HtmlSignals | None,
) -> WebsiteQualityResult:
    limitations: list[str] = []

    if site_state != DataState.CONFIRMED or fetch is None:
        return WebsiteQualityResult(
            score=None,
            components={},
            signals={},
            confidence=None,
            limitations=[
                f"site não confirmado como acessível (estado: {site_state.value}) — "
                "nenhum score foi calculado; isso não deve ser lido como 'site ruim'."
            ],
        )

    is_html = is_html_content_type(fetch.content_type)
    if not is_html or html is None:
        limitations.append(
            f"conteúdo não é HTML analisável (content-type: {fetch.content_type!r}) — "
            "dimensões de SEO/conteúdo/UX ficaram em zero por falta de sinal, não por serem ruins."
        )
        html = html or HtmlSignals()

    if fetch.truncated:
        limitations.append("resposta truncada pelo limite de tamanho configurado — sinais podem estar incompletos.")

    if html.image_count == 0:
        limitations.append("sem imagens na página — proporção de alt text não avaliável.")

    if fetch.status_code != 200:
        limitations.append(f"a página respondeu com status HTTP {fetch.status_code}, não 200.")

    components = {
        "security": _score_security(fetch),
        "seo": _score_seo(html),
        "content": _score_content(html),
        "ux": _score_ux(html),
        "technical": _score_technical(fetch),
    }

    overall = sum(components[name] * weight for name, weight in _WEIGHTS.items())

    if not is_html:
        confidence = ConfidenceLevel.LOW
    elif fetch.truncated or fetch.status_code != 200:
        confidence = ConfidenceLevel.MEDIUM
    else:
        confidence = ConfidenceLevel.HIGH

    signals = {
        "https": fetch.is_https,
        "status_code": fetch.status_code,
        "content_type": fetch.content_type,
        "response_time_ms": round(fetch.elapsed_ms, 1),
        "truncated": fetch.truncated,
        "redirect_count": len(fetch.redirect_chain),
        "title": html.title,
        "title_length": len(html.title) if html.title else 0,
        "meta_description_present": bool(html.meta_description),
        "meta_description_length": len(html.meta_description) if html.meta_description else 0,
        "canonical_present": bool(html.canonical),
        "language": html.language,
        "viewport_present": html.viewport_present,
        "robots_meta_blocking": html.robots_meta_blocking,
        "favicon_present": html.favicon_present,
        "heading_count": html.heading_count,
        "h1_count": html.h1_count,
        "image_count": html.image_count,
        "image_alt_ratio": html.image_alt_ratio,
        "form_present": html.form_present,
        "internal_link_count": html.internal_link_count,
        "external_link_count": html.external_link_count,
        "social_links": html.social_links,
        "phone_like_text_found": html.phone_like_text_found,
        "contact_link_found": html.contact_link_found,
    }

    return WebsiteQualityResult(
        score=round(overall, 1),
        components={name: round(value, 1) for name, value in components.items()},
        signals=signals,
        confidence=confidence,
        limitations=limitations,
    )
