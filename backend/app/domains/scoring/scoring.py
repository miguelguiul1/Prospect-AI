"""Opportunity Score: metodologia determinística e explicável.

**O que este score É**: uma heurística de PRIORIZAÇÃO COMERCIAL — um número
0-100 que ajuda a decidir em qual ordem abordar prospects já descobertos e
identificados, combinando sinais públicos e observáveis já coletados pelas
Fases 1-3 (Discovery, Identity Resolution, Digital Audit/Evidence Layer).

**O que este score NÃO é** (arquitetura v0.2; reafirmado no Prompt 07):
não é uma probabilidade estatística de conversão, não é uma estimativa de
faturamento/orçamento/capacidade de compra do prospect, e não é o Website
Quality Score (Fase 3) — aquele mede só qualidade técnica de UM website; este
combina o Website Quality Score com outros sinais para estimar prioridade de
venda. `rating`/`review_count` entram aqui como sinais de VISIBILIDADE/
tração pública (evidência de que o negócio é real, ativo e encontrável) —
nunca como proxy de dinheiro disponível.

**Determinismo.** `compute_opportunity_score` é uma função pura: a mesma
`ScoringContext` sempre produz o mesmo resultado. Nenhuma IA participa deste
cálculo (o único componente que usa IA na Fase 4 é o Sales Brief, um
domínio inteiramente separado — `app.domains.briefing`).

**Dimensões, pesos e por quê.**

| Dimensão | Peso | Por quê esse peso |
|---|---|---|
| Website Gap | 25% | A ausência (ou inacessibilidade) de um site próprio é o sinal mais direto de que a agência tem algo a vender — pesa mais que qualquer outro. |
| Website Quality Gap | 20% | Um site que existe mas é tecnicamente ruim (Fase 3) também é oportunidade, só que menor que "não ter site nenhum". |
| Digital Presence Gap | 15% | Ter presença em rede social/agregador mas não em domínio próprio é um gancho comercial claro ("converta seus seguidores em um site que você controla"), mas mais fraco que os dois acima porque a Fase 1-3 não têm um provider dedicado de redes sociais — o sinal vem só do valor de "website" já coletado. |
| Business Visibility | 15% | `rating`/`review_count` como indício de que o negócio é real/ativo/relevante o suficiente para valer o esforço de prospecção — nunca como orçamento. Peso deliberadamente moderado para não deixar esse sinal dominar o score (ver `docs/opportunity-scoring.md`, "por que reviews não é receita"). |
| Segment Fit | 15% | Categorias historicamente mais responsivas a serviços de site/marketing digital recebem uma leve vantagem — tabela pequena e explícita, não uma nova taxonomia. |
| Contactability | 10% | Menor peso de propósito: descreve se é FÁCIL abordar o prospect (temos telefone/endereço/contato público), não se vale a pena abordá-lo. |

Pesos somam 1.0 exatamente quando as 6 dimensões têm dado disponível. Uma
dimensão sem evidência suficiente é EXCLUÍDA do cálculo (nunca vira 0 nem
100 por suposição) e os pesos restantes são renormalizados — o mesmo
princípio de "ausência não é evidência de nada" do Evidence Layer (Fase 0)
aplicado ao scoring. `confidence` comunica quantas dimensões estavam
disponíveis; o score em si nunca é artificialmente "puxado para o meio" só
por causa de dados faltantes — isso seria inventar um valor. Ver
`docs/opportunity-scoring.md` para a discussão completa dessa escolha.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.domains.audit.models import WebsiteQuality
from app.domains.discovery.normalization import is_trusted_website
from app.domains.evidence.enums import ConfidenceLevel, DataState
from app.domains.scoring.models import SCORING_VERSION

WEIGHTS: dict[str, float] = {
    "website_gap": 0.25,
    "website_quality_gap": 0.20,
    "digital_presence_gap": 0.15,
    "business_visibility": 0.15,
    "segment_fit": 0.15,
    "contactability": 0.10,
}

# Faixas de classificação (0-100), avaliadas da mais alta para a mais baixa.
# Hipótese inicial documentada — não um resultado de dados reais, no mesmo
# espírito dos limiares de Identity Resolution (Fase 2) e dos pesos do
# Website Quality Score (Fase 3): todos aguardam recalibração quando houver
# dados reais de conversão de vendas.
_TIER_BANDS: list[tuple[float, str]] = [
    (80.0, "high"),
    (60.0, "medium_high"),
    (40.0, "medium"),
    (20.0, "low"),
    (0.0, "very_low"),
]

# Tabela pequena e explícita de adequação de segmento (0-100) — não uma nova
# taxonomia. Reaproveita `Category.slug` (Fase 0/1), sem introduzir nenhuma
# tabela nova. Categorias fora desta lista recebem o valor neutro
# `_SEGMENT_FIT_DEFAULT`, marcado como tal no `reason` do breakdown (nunca
# tratado com a mesma confiança de uma categoria mapeada explicitamente).
# Hipótese inicial baseada no perfil de cliente de uma agência de
# desenvolvimento web (negócios locais com forte dependência de presença
# digital para conversão) — não um resultado de dados reais.
SEGMENT_FIT_SCORES: dict[str, float] = {
    "restaurante": 80.0,
    "restaurantes": 80.0,
    "barbearia": 85.0,
    "barbearias": 85.0,
    "salao de beleza": 85.0,
    "clinica": 75.0,
    "clinicas": 75.0,
    "consultorio": 75.0,
    "dentista": 75.0,
    "academia": 75.0,
    "academias": 75.0,
    "pet shop": 80.0,
    "petshop": 80.0,
    "advocacia": 65.0,
    "contabilidade": 60.0,
    "imobiliaria": 65.0,
    "hotel": 60.0,
    "pousada": 65.0,
}
SEGMENT_FIT_DEFAULT = 50.0

# Sinal máximo de `review_count` considerado antes de saturar (ver
# `_score_business_visibility`) — evita que um único negócio com milhares de
# avaliações domine o dimensionamento; o objetivo é distinguir "tem alguma
# tração pública" de "não tem nenhuma", não ranquear por popularidade.
_REVIEW_COUNT_SATURATION = 50.0


@dataclass(frozen=True)
class DimensionResult:
    """Resultado de uma dimensão: `None` em `raw`/`contribution` quando a
    dimensão foi excluída do cálculo por falta de evidência suficiente."""

    raw: float | None
    weight: float
    contribution: float | None
    reason: str
    evidence_refs: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "raw": self.raw,
            "weight": self.weight,
            "contribution": self.contribution,
            "reason": self.reason,
            "evidence_refs": self.evidence_refs,
        }


@dataclass(frozen=True)
class EvidenceRef:
    field: str
    value: str | None
    evidence_id: str | None = None

    def to_dict(self) -> dict:
        return {"field": self.field, "value": self.value, "evidence_id": self.evidence_id}


@dataclass(frozen=True)
class ScoringContext:
    """Todo o dado necessário para calcular o Opportunity Score de UMA
    execução de auditoria — nunca coleta nada novo, só lê o que Discovery/
    Identity Resolution/Digital Audit/Evidence Layer já produziram."""

    site_state: DataState
    website_quality: WebsiteQuality | None
    website_value: EvidenceRef | None  # Evidence(field="website") atual, não filtrada por confiabilidade
    category_slug: str | None
    rating: EvidenceRef | None
    review_count: EvidenceRef | None
    phone: EvidenceRef | None
    address: EvidenceRef | None
    website_contact_available: EvidenceRef | None


@dataclass(frozen=True)
class OpportunityScoreResult:
    score: float | None
    tier: str | None
    confidence: ConfidenceLevel
    breakdown: dict


def _refs(*refs: EvidenceRef | None) -> list[dict]:
    return [r.to_dict() for r in refs if r is not None]


def _score_website_gap(ctx: ScoringContext) -> DimensionResult:
    state = ctx.site_state
    mapping = {
        DataState.NOT_DETECTED: (100.0, "nenhum site próprio foi detectado — maior oportunidade direta."),
        DataState.INACCESSIBLE: (80.0, "um site foi indicado mas está inacessível no momento da auditoria."),
        DataState.INCONCLUSIVE: (50.0, "o candidato a site encontrado é ambíguo — valor conservador por falta de certeza."),
        DataState.NOT_CHECKED: (50.0, "auditoria ainda não confirmou o site (bloqueado por política de segurança ou não executada) — valor conservador."),
        DataState.STALE: (50.0, "última confirmação de site expirou e precisa ser reconfirmada — valor conservador."),
        DataState.CONFIRMED: (0.0, "site próprio confirmado e acessível — sem gap de existência (qualidade é avaliada à parte)."),
    }
    raw, reason = mapping[state]
    weight = WEIGHTS["website_gap"]
    return DimensionResult(raw=raw, weight=weight, contribution=raw * weight, reason=reason)


def _score_website_quality_gap(ctx: ScoringContext) -> DimensionResult:
    weight = WEIGHTS["website_quality_gap"]
    quality = ctx.website_quality
    if ctx.site_state != DataState.CONFIRMED or quality is None or quality.score is None:
        return DimensionResult(
            raw=None, weight=weight, contribution=None,
            reason="site não confirmado como acessível — Website Quality Score (Fase 3) não existe para esta execução; dimensão excluída, não assumida como 0 ou 100.",
        )
    gap = round(100.0 - quality.score, 1)
    return DimensionResult(
        raw=gap, weight=weight, contribution=gap * weight,
        reason=f"Website Quality Score = {quality.score} → gap de qualidade = {gap}.",
        evidence_refs=[{"field": "website_quality.score", "value": quality.score, "evidence_id": str(quality.id)}],
    )


def _score_digital_presence_gap(ctx: ScoringContext) -> DimensionResult:
    weight = WEIGHTS["digital_presence_gap"]
    website = ctx.website_value

    if website is None or not website.value:
        return DimensionResult(
            raw=None, weight=weight, contribution=None,
            reason="nenhuma evidência de presença digital (site ou rede social) foi coletada — dimensão excluída.",
        )

    if not is_trusted_website(website.value):
        raw = 90.0
        reason = (
            "o valor de 'website' coletado aponta para uma rede social/agregador, não um domínio próprio — "
            "presença digital existe, mas não está convertida em um canal próprio."
        )
    elif ctx.site_state == DataState.CONFIRMED:
        raw = 10.0
        reason = "possui site em domínio próprio confirmado e acessível — presença já convertida em canal próprio."
    else:
        raw = 50.0
        reason = "um domínio próprio foi informado, mas a auditoria não confirmou acessibilidade."

    return DimensionResult(raw=raw, weight=weight, contribution=raw * weight, reason=reason, evidence_refs=_refs(website))


def _score_business_visibility(ctx: ScoringContext) -> DimensionResult:
    weight = WEIGHTS["business_visibility"]
    rating_ref, review_ref = ctx.rating, ctx.review_count

    rating = float(rating_ref.value) if rating_ref and rating_ref.value else None
    review_count = int(float(review_ref.value)) if review_ref and review_ref.value else None

    if rating is None and review_count is None:
        return DimensionResult(
            raw=None, weight=weight, contribution=None,
            reason="sem avaliações/contagem de avaliações coletadas — dimensão excluída.",
        )

    review_component = min((review_count or 0) / _REVIEW_COUNT_SATURATION, 1.0) * 70.0
    rating_component = max(0.0, min((rating or 0.0) / 5.0, 1.0)) * 30.0
    raw = round(review_component + rating_component, 1)

    reason = (
        f"{review_count if review_count is not None else 'sem contagem de'} avaliações públicas, "
        f"nota {rating if rating is not None else 'desconhecida'}/5 — usado só como indício de que o negócio é "
        "real/ativo/encontrável; NUNCA como proxy de faturamento ou orçamento disponível."
    )
    return DimensionResult(raw=raw, weight=weight, contribution=raw * weight, reason=reason, evidence_refs=_refs(rating_ref, review_ref))


def _score_segment_fit(ctx: ScoringContext) -> DimensionResult:
    weight = WEIGHTS["segment_fit"]
    if not ctx.category_slug:
        return DimensionResult(
            raw=None, weight=weight, contribution=None,
            reason="empresa sem categoria atribuída — dimensão excluída.",
        )

    key = ctx.category_slug.strip().lower().replace("-", " ")
    if key in SEGMENT_FIT_SCORES:
        raw = SEGMENT_FIT_SCORES[key]
        reason = f"categoria '{ctx.category_slug}' mapeada explicitamente na tabela de adequação de segmento."
    else:
        raw = SEGMENT_FIT_DEFAULT
        reason = (
            f"categoria '{ctx.category_slug}' não está na tabela de adequação de segmento — "
            f"valor neutro padrão ({SEGMENT_FIT_DEFAULT}) usado, não uma avaliação real desta categoria."
        )
    return DimensionResult(raw=raw, weight=weight, contribution=raw * weight, reason=reason)


def _score_contactability(ctx: ScoringContext) -> DimensionResult:
    weight = WEIGHTS["contactability"]
    raw = 0.0
    parts: list[str] = []

    if ctx.phone and ctx.phone.value:
        raw += 50.0
        parts.append("telefone público conhecido")
    if ctx.address and ctx.address.value:
        raw += 25.0
        parts.append("endereço público conhecido")
    if ctx.website_contact_available and ctx.website_contact_available.value == "true":
        raw += 25.0
        parts.append("canal de contato encontrado no próprio site")

    raw = min(raw, 100.0)
    reason = (
        ("; ".join(parts) + " — facilidade de abordagem, não avalia se vale a pena abordar.")
        if parts
        else "nenhum canal público de contato conhecido — tratado como fato observado (Discovery tenta coletar telefone/endereço sempre), não como 'não verificado'."
    )
    return DimensionResult(
        raw=raw, weight=weight, contribution=raw * weight, reason=reason,
        evidence_refs=_refs(ctx.phone, ctx.address, ctx.website_contact_available),
    )


_DIMENSION_SCORERS = {
    "website_gap": _score_website_gap,
    "website_quality_gap": _score_website_quality_gap,
    "digital_presence_gap": _score_digital_presence_gap,
    "business_visibility": _score_business_visibility,
    "segment_fit": _score_segment_fit,
    "contactability": _score_contactability,
}


def classify(score: float) -> str:
    for threshold, tier in _TIER_BANDS:
        if score >= threshold:
            return tier
    return "very_low"  # inalcançável (score sempre >= 0), mantido por segurança


def _compute_confidence(site_state: DataState, available_count: int) -> ConfidenceLevel:
    """Reflete quantidade/qualidade de sinal disponível — nunca o valor do
    score em si (um score alto com confiança baixa é uma combinação válida e
    esperada, ex.: poucos sinais mas todos apontando na mesma direção)."""
    if site_state in (DataState.NOT_CHECKED, DataState.INCONCLUSIVE):
        return ConfidenceLevel.LOW
    if available_count >= 5:
        return ConfidenceLevel.HIGH
    if available_count >= 3:
        return ConfidenceLevel.MEDIUM
    return ConfidenceLevel.LOW


def compute_opportunity_score(ctx: ScoringContext) -> OpportunityScoreResult:
    dimensions = {name: scorer(ctx) for name, scorer in _DIMENSION_SCORERS.items()}

    available = [d for d in dimensions.values() if d.contribution is not None]
    total_weight = sum(d.weight for d in available)

    if not available or total_weight <= 0:
        # Website Gap e Contactability são calculados sempre (nunca `None`),
        # então este ramo é inalcançável em uso normal — mantido por
        # segurança para nunca dividir por zero.
        breakdown = {
            "scoring_version": SCORING_VERSION,
            "dimensions": {name: d.to_dict() for name, d in dimensions.items()},
            "final_score": None,
            "available_weight": 0.0,
        }
        return OpportunityScoreResult(score=None, tier=None, confidence=ConfidenceLevel.LOW, breakdown=breakdown)

    weighted_sum = sum(d.contribution for d in available)
    final_score = round(weighted_sum / total_weight, 1)
    final_score = max(0.0, min(final_score, 100.0))

    confidence = _compute_confidence(ctx.site_state, len(available))
    tier = classify(final_score)

    breakdown = {
        "scoring_version": SCORING_VERSION,
        "dimensions": {name: d.to_dict() for name, d in dimensions.items()},
        "final_score": final_score,
        "available_weight": round(total_weight, 4),
        "available_dimension_count": len(available),
    }

    return OpportunityScoreResult(score=final_score, tier=tier, confidence=confidence, breakdown=breakdown)


__all__ = [
    "WEIGHTS",
    "SEGMENT_FIT_SCORES",
    "SEGMENT_FIT_DEFAULT",
    "ScoringContext",
    "EvidenceRef",
    "OpportunityScoreResult",
    "compute_opportunity_score",
    "classify",
]
