"""Context Builder da geração de Prototype por IA (Fase 9 / Prompt 11).

`PrototypeContextBuilder.build(company_id)` monta um `PrototypeContext` —
o ÚNICO material que o Generation Engine (`app.domains.prototypes.
generation`) recebe para escrever a árvore de componentes. Nenhum dado
além do que está aqui chega ao prompt: nunca o HTML bruto de uma página
(só os `HtmlSignals` já extraídos pela Fase 3), nunca um candidato bruto
de Discovery (só a `Company` já resolvida), nunca uma tabela inteira.

Regra central deste módulo, a mais importante da fase inteira: TODO campo
carrega uma classificação de confiança — nunca um valor "pelado" que
disfarça incerteza como certeza.

    FACT       confirmado (ex.: nome da empresa; um telefone com
               Evidence.state=CONFIRMED e confidence=HIGH).
    SIGNAL     indício público, não uma certeza (ex.: um telefone
               observado mas com confiança MEDIUM/LOW; "o site menciona
               entrega"; o próprio estado do site quando não CONFIRMED —
               "auditoria tentou e não confirmou" já é, em si, um sinal
               útil, não a ausência de informação).
    UNKNOWN    não observado — a checagem correspondente nunca aconteceu,
               ou a Evidence não tem valor. NUNCA omitido: o campo aparece
               no contexto marcado como UNKNOWN, nunca como `None` mudo.
    INFERENCE  inferência controlada e explicitamente rotulada — usada só
               para dois casos desta fase, ambos com a origem sempre
               visível: (1) uma `Evidence` cujo `method=INFERENCE` (o
               próprio Digital Audit já marcou como inferido, não
               observado); (2) o `recommended_product` do Opportunity
               Score e o conteúdo do Sales Brief mais recente — ambos são
               SAÍDA de um sistema (determinístico ou de IA) sobre a
               empresa, nunca um fato observado diretamente dela.

Campo obrigatório vs. opcional (decisão desta fase, ver
`InsufficientContextError`): o único campo tecnicamente obrigatório é
`company_name` (`Company.canonical_name` é `NOT NULL` no banco — nunca
pode faltar). Isso sozinho não é suficiente, porém: um contexto com nome
mas ZERO Evidence e ZERO AuditSnapshot não daria ao Generation Engine
absolutamente nada para fundamentar o protótipo além do nome — geraria
"praticamente vazio disfarçado de sucesso" (a frase exata da instrução
desta fase). Por isso a construção do contexto FALHA explicitamente
(`InsufficientContextError`) quando a empresa não tem nenhuma Evidence
nem nenhum `AuditSnapshot` — o mínimo de material real para gerar algo
grounded. Todos os outros campos são opcionais e viram `UNKNOWN` quando
ausentes, nunca lançam erro nem são omitidos da estrutura.
"""
from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy.orm import Session

from app.domains.companies.models import Company
from app.domains.companies.queries import CompanyDetail, get_company_detail
from app.domains.evidence.enums import ConfidenceLevel, DataState, EvidenceMethod
from app.domains.evidence.models import Evidence
from app.domains.evidence.queries import get_current_evidence

CONTEXT_VERSION = "v1"

# Mesmos campos já lidos por `app.domains.briefing.service` — reaproveitados
# aqui para nunca divergir de qual Evidence "importa" para descrever uma
# empresa entre os dois domínios que fazem isso (Sales Brief e Prototype).
_EVIDENCE_FIELDS = [
    "phone",
    "address",
    "website",
    "website_title",
    "website_meta_description",
    "website_contact_available",
    "website_social_links",
]


class ContextConfidence(str, enum.Enum):
    FACT = "fact"
    SIGNAL = "signal"
    UNKNOWN = "unknown"
    INFERENCE = "inference"


@dataclass(frozen=True)
class ContextField:
    """Um único dado do contexto, sempre com confiança e origem visíveis.

    `source` é o "provenance" pedido pela fase: de qual domínio/tabela/
    coluna este valor veio (ex.: `"evidence:phone"`,
    `"company.canonical_name"`, `"opportunity_score.recommended_product"`)
    — o que permite reconstruir, meses depois, exatamente de onde cada
    afirmação do protótipo gerado se origina (junto com `ContextSnapshot`,
    seção 4 do Prompt 11)."""

    value: str | float | int | bool | list[str] | None
    confidence: ContextConfidence
    source: str


def _unknown(source: str) -> ContextField:
    return ContextField(value=None, confidence=ContextConfidence.UNKNOWN, source=source)


@dataclass(frozen=True)
class PrototypeContext:
    """Todo o material que o Generation Engine recebe — nada além disto
    chega ao prompt (ver docstring do módulo)."""

    company_id: uuid.UUID
    context_version: str

    company_name: ContextField
    category: ContextField
    region: ContextField
    site_state: ContextField
    website_url: ContextField
    phone: ContextField
    address: ContextField
    website_title: ContextField
    website_meta_description: ContextField
    contact_available: ContextField
    social_links: ContextField

    opportunity_tier: ContextField
    opportunity_score: ContextField
    recommended_product: ContextField

    sales_brief_summary: ContextField
    sales_brief_suggested_angle: ContextField

    # Data da evidência mais antiga usada neste contexto — nunca a mais
    # recente: o propósito é sinalizar o pior caso de "desatualização" do
    # material usado, não o melhor.
    freshness: datetime | None

    def all_fields(self) -> dict[str, ContextField]:
        return {
            name: value
            for name, value in vars(self).items()
            if isinstance(value, ContextField)
        }

    def to_dict(self) -> dict:
        """Serialização JSON-segura para `ContextSnapshot` (seção 4 do
        Prompt 11) — grava o `PrototypeContext` INTEIRO, imutável, para
        que seja possível responder "por que a IA colocou isso aí" meses
        depois, mesmo que a Evidence da empresa já tenha mudado."""
        return {
            "company_id": str(self.company_id),
            "context_version": self.context_version,
            "freshness": self.freshness.isoformat() if self.freshness else None,
            "fields": {
                name: {"value": field.value, "confidence": field.confidence.value, "source": field.source}
                for name, field in self.all_fields().items()
            },
        }


class InsufficientContextError(ValueError):
    """A empresa não tem nenhuma Evidence nem nenhum AuditSnapshot — dado
    real insuficiente para gerar algo grounded (ver docstring do módulo)."""


def _confidence_from_evidence(evidence: Evidence | None) -> ContextConfidence:
    if evidence is None or evidence.value is None:
        return ContextConfidence.UNKNOWN
    if evidence.state != DataState.CONFIRMED:
        # Uma checagem foi de fato tentada e voltou algo diferente de
        # "confirmado" (inconclusivo/inacessível/etc.) — isso É um sinal
        # público real, não a ausência de dado (ver docstring do módulo).
        return ContextConfidence.SIGNAL
    if evidence.method == EvidenceMethod.INFERENCE:
        return ContextConfidence.INFERENCE
    if evidence.confidence == ConfidenceLevel.HIGH:
        return ContextConfidence.FACT
    return ContextConfidence.SIGNAL


def _field_from_evidence(evidence: Evidence | None, *, source: str) -> ContextField:
    if evidence is None:
        return _unknown(source)
    return ContextField(value=evidence.value, confidence=_confidence_from_evidence(evidence), source=source)


class PrototypeContextBuilder:
    def __init__(self, db: Session) -> None:
        self._db = db

    def build(self, company_id: uuid.UUID) -> PrototypeContext:
        detail = get_company_detail(self._db, company_id)
        if detail is None:
            raise LookupError(f"Company {company_id} não encontrada")

        if not detail.evidence and detail.latest_audit is None:
            raise InsufficientContextError(
                f"Company {company_id} não tem nenhuma Evidence nem nenhum AuditSnapshot — "
                "dado insuficiente para gerar um protótipo com fundamento real. Rode uma busca "
                "de Discovery e/ou um Digital Audit para esta empresa antes de gerar."
            )

        evidence_by_field = self._evidence_by_field(company_id, detail)

        return PrototypeContext(
            company_id=company_id,
            context_version=CONTEXT_VERSION,
            company_name=ContextField(
                value=detail.company.canonical_name,
                confidence=ContextConfidence.FACT,
                source="company.canonical_name",
            ),
            category=self._category_field(detail.company),
            region=self._region_field(detail.company),
            site_state=self._site_state_field(detail),
            website_url=self._website_url_field(detail),
            phone=_field_from_evidence(evidence_by_field.get("phone"), source="evidence:phone"),
            address=_field_from_evidence(evidence_by_field.get("address"), source="evidence:address"),
            website_title=_field_from_evidence(
                evidence_by_field.get("website_title"), source="evidence:website_title"
            ),
            website_meta_description=_field_from_evidence(
                evidence_by_field.get("website_meta_description"), source="evidence:website_meta_description"
            ),
            contact_available=_field_from_evidence(
                evidence_by_field.get("website_contact_available"), source="evidence:website_contact_available"
            ),
            social_links=self._social_links_field(evidence_by_field.get("website_social_links")),
            opportunity_tier=self._tier_field(detail),
            opportunity_score=self._score_field(detail),
            recommended_product=self._recommended_product_field(detail),
            sales_brief_summary=self._brief_field(detail, key="summary"),
            sales_brief_suggested_angle=self._brief_field(detail, key="suggested_angle"),
            freshness=self._freshness(detail),
        )

    def _evidence_by_field(self, company_id: uuid.UUID, detail: CompanyDetail) -> dict[str, Evidence]:
        """Reaproveita a lista já carregada por `get_company_detail`
        (evita N+1 consultas) quando possível; cai para uma consulta
        direta por campo só para os campos que essa lista não cobrir —
        na prática nunca acontece hoje (a lista já é "toda Evidence atual
        da empresa"), mas protege contra o caso de `_EVIDENCE_FIELDS`
        crescer no futuro sem alguém lembrar de checar esta função."""
        by_field = {e.field: e for e in detail.evidence}
        for field_name in _EVIDENCE_FIELDS:
            if field_name not in by_field:
                found = get_current_evidence(self._db, company_id, field_name)
                if found is not None:
                    by_field[field_name] = found
        return by_field

    def _category_field(self, company: Company) -> ContextField:
        if company.category is None:
            return _unknown("company.category")
        return ContextField(value=company.category.name, confidence=ContextConfidence.FACT, source="company.category")

    def _region_field(self, company: Company) -> ContextField:
        if company.region is None:
            return _unknown("company.region")
        return ContextField(value=company.region.name, confidence=ContextConfidence.FACT, source="company.region")

    def _site_state_field(self, detail: CompanyDetail) -> ContextField:
        if detail.latest_audit is None or detail.latest_audit.site_state is None:
            return _unknown("audit_snapshot.site_state")
        state = detail.latest_audit.site_state
        confidence = ContextConfidence.FACT if state == DataState.CONFIRMED else ContextConfidence.SIGNAL
        return ContextField(value=state.value, confidence=confidence, source="audit_snapshot.site_state")

    def _website_url_field(self, detail: CompanyDetail) -> ContextField:
        if detail.latest_audit is None or not detail.latest_audit.website_url:
            return _unknown("audit_snapshot.website_url")
        return ContextField(
            value=detail.latest_audit.website_url, confidence=ContextConfidence.FACT, source="audit_snapshot.website_url"
        )

    def _social_links_field(self, evidence: Evidence | None) -> ContextField:
        if evidence is None or not evidence.value:
            return _unknown("evidence:website_social_links")
        # Persistido como string separada por vírgula (ver
        # app.domains.audit.persistence) — nunca reformatado como JSON só
        # para este consumo, para não divergir de como o resto do sistema
        # lê o mesmo campo.
        links = [item.strip() for item in evidence.value.split(",") if item.strip()]
        return ContextField(
            value=links, confidence=_confidence_from_evidence(evidence), source="evidence:website_social_links"
        )

    def _tier_field(self, detail: CompanyDetail) -> ContextField:
        if detail.latest_score is None or detail.latest_score.tier is None:
            return _unknown("opportunity_score.tier")
        return ContextField(
            value=detail.latest_score.tier.value, confidence=ContextConfidence.FACT, source="opportunity_score.tier"
        )

    def _score_field(self, detail: CompanyDetail) -> ContextField:
        if detail.latest_score is None or detail.latest_score.score is None:
            return _unknown("opportunity_score.score")
        return ContextField(
            value=detail.latest_score.score, confidence=ContextConfidence.FACT, source="opportunity_score.score"
        )

    def _recommended_product_field(self, detail: CompanyDetail) -> ContextField:
        if detail.latest_score is None or not detail.latest_score.recommended_product:
            return _unknown("opportunity_score.recommended_product")
        # INFERENCE, não FACT: é uma recomendação heurística calculada pelo
        # Opportunity Score, não um fato observado sobre a empresa (ver
        # docstring do módulo).
        return ContextField(
            value=detail.latest_score.recommended_product,
            confidence=ContextConfidence.INFERENCE,
            source="opportunity_score.recommended_product",
        )

    def _brief_field(self, detail: CompanyDetail, *, key: str) -> ContextField:
        source = f"sales_brief.{key}"
        brief = detail.latest_brief
        if brief is None or brief.status.value != "completed" or not brief.content:
            return _unknown(source)
        value = brief.content.get(key)
        if not value:
            return _unknown(source)
        # INFERENCE: conteúdo de um Sales Brief é, ele mesmo, uma saída de
        # IA sobre a empresa — nunca tratado como fato observado (ver
        # docstring do módulo).
        return ContextField(value=value, confidence=ContextConfidence.INFERENCE, source=source)

    def _freshness(self, detail: CompanyDetail) -> datetime | None:
        timestamps = [e.collected_at for e in detail.evidence]
        if detail.latest_audit is not None:
            timestamps.append(detail.latest_audit.created_at)
        return min(timestamps) if timestamps else None


__all__ = [
    "CONTEXT_VERSION",
    "ContextConfidence",
    "ContextField",
    "PrototypeContext",
    "PrototypeContextBuilder",
    "InsufficientContextError",
]
