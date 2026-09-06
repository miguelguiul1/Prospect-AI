"""Orquestração do Sales Brief:

Company -> OpportunityScore mais recente -> AuditSnapshot/WebsiteQuality +
Evidence atual -> BriefingContext -> prompt -> provider de IA -> validação
(`SalesBriefContent`) -> `SalesBrief` persistido.

Este é o ÚNICO domínio da Fase 4 (e de todo o Prospect AI até aqui) que
chama um provider de IA. Falha de provider, timeout ou resposta inválida
NUNCA vira um brief falso — sempre um `SalesBrief.status=FAILED` com o
motivo registrado (arquitetura Fase 4: "nunca mascarar falha como
sucesso").
"""
from __future__ import annotations

import json
import uuid

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.domains.audit.models import AuditSnapshot
from app.domains.briefing.models import SalesBrief, SalesBriefStatus
from app.domains.briefing.prompt import PROMPT_VERSION, BriefingContext, build_prompt
from app.domains.briefing.providers import get_provider
from app.domains.briefing.providers.base import SalesBriefProvider
from app.domains.briefing.providers.errors import SalesBriefProviderError
from app.domains.briefing.schemas import SalesBriefContent
from app.domains.companies.models import Company
from app.domains.evidence.queries import get_current_value
from app.domains.scoring.models import OpportunityScore
from app.domains.scoring.service import OpportunityScoringService

logger = get_logger(__name__)

_EVIDENCE_FIELDS = [
    "phone",
    "address",
    "website",
    "rating",
    "review_count",
    "website_title",
    "website_meta_description",
    "website_contact_available",
    "website_social_links",
]


class SalesBriefService:
    def __init__(
        self,
        db: Session,
        *,
        settings: Settings | None = None,
        provider: SalesBriefProvider | None = None,
    ) -> None:
        self._db = db
        self._settings = settings or get_settings()
        # Injetável só para testes (um provider falso/mockado) — em
        # produção, `get_provider` decide a implementação real.
        self._provider = provider

    def _latest_opportunity_score(self, company_id: uuid.UUID) -> OpportunityScore | None:
        return OpportunityScoringService(self._db).get_latest(company_id)

    def build_context(self, company: Company, score: OpportunityScore) -> BriefingContext:
        snapshot: AuditSnapshot = score.audit_snapshot
        quality = snapshot.website_quality

        breakdown_reasons: dict[str, str] = {}
        if score.breakdown:
            for dimension, data in (score.breakdown.get("dimensions") or {}).items():
                if isinstance(data, dict) and data.get("reason"):
                    breakdown_reasons[dimension] = data["reason"]

        evidence = {field: get_current_value(self._db, company.id, field) for field in _EVIDENCE_FIELDS}

        return BriefingContext(
            company_name=company.canonical_name,
            category=company.category.name if company.category else None,
            region=company.region.name if company.region else None,
            site_state=snapshot.site_state.value if snapshot.site_state else "desconhecido",
            website_url=snapshot.website_url,
            website_quality_score=quality.score if quality else None,
            website_quality_limitations=(quality.limitations or []) if quality else [],
            opportunity_score=score.score,
            opportunity_tier=score.tier.value if score.tier else None,
            opportunity_confidence=score.confidence.value if score.confidence else None,
            opportunity_breakdown_reasons=breakdown_reasons,
            evidence=evidence,
        )

    def validate_preconditions(self, company_id: uuid.UUID) -> tuple[Company, OpportunityScore]:
        """Checagens que devem acontecer de forma síncrona, ANTES de
        enfileirar/executar a chamada ao provider — mesmo espírito de
        `DigitalAuditService.start_audit` (Fase 3): erros de precondição
        (`LookupError`/`ValueError`) devem virar 404/409 imediatos na API,
        nunca uma falha descoberta só depois de um job já ter sido
        enfileirado."""
        company = self._db.get(Company, company_id)
        if company is None:
            raise LookupError(f"Company {company_id} não encontrada")

        score = self._latest_opportunity_score(company_id)
        if score is None:
            raise ValueError(
                f"Company {company_id} não tem nenhum Opportunity Score calculado ainda — "
                "rode POST /api/scoring/{company_id} antes de gerar o Sales Brief."
            )
        return company, score

    def generate(self, company_id: uuid.UUID) -> SalesBrief:
        company, score = self.validate_preconditions(company_id)

        context = self.build_context(company, score)
        prompt = build_prompt(context)
        provider = self._provider or get_provider(self._settings)

        try:
            response = provider.generate(system=prompt["system"], user=prompt["user"])
            content = self._validate_content(response.content)
        except SalesBriefProviderError as exc:
            return self._persist_failure(
                company_id=company_id,
                opportunity_score_id=score.id,
                provider_name=getattr(provider, "name", None),
                error_code=exc.__class__.__name__,
                error_message=str(exc)[:500],
            )

        brief = SalesBrief(
            company_id=company_id,
            opportunity_score_id=score.id,
            status=SalesBriefStatus.COMPLETED,
            content=content.model_dump(),
            provider=getattr(provider, "name", None),
            model=response.model,
            prompt_version=PROMPT_VERSION,
            duration_ms=response.duration_ms,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
        )
        self._db.add(brief)
        self._db.flush()

        logger.info(
            "sales_brief_generated",
            company_id=str(company_id),
            opportunity_score_id=str(score.id),
            provider=brief.provider,
            model=brief.model,
        )
        return brief

    def _validate_content(self, raw_text: str) -> SalesBriefContent:
        from app.domains.briefing.providers.errors import ProviderInvalidResponseError

        try:
            payload = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise ProviderInvalidResponseError(f"Resposta do provider não é JSON válido: {exc}") from exc

        try:
            return SalesBriefContent.model_validate(payload)
        except ValidationError as exc:
            raise ProviderInvalidResponseError(f"Resposta do provider não validou contra o schema esperado: {exc}") from exc

    def _persist_failure(
        self,
        *,
        company_id: uuid.UUID,
        opportunity_score_id: uuid.UUID,
        provider_name: str | None,
        error_code: str,
        error_message: str,
    ) -> SalesBrief:
        brief = SalesBrief(
            company_id=company_id,
            opportunity_score_id=opportunity_score_id,
            status=SalesBriefStatus.FAILED,
            content=None,
            provider=provider_name,
            prompt_version=PROMPT_VERSION,
            error_code=error_code,
            error_message=error_message,
        )
        self._db.add(brief)
        self._db.flush()

        logger.warning(
            "sales_brief_failed",
            company_id=str(company_id),
            opportunity_score_id=str(opportunity_score_id),
            error_code=error_code,
        )
        return brief

    def get_latest(self, company_id: uuid.UUID) -> SalesBrief | None:
        return (
            self._db.query(SalesBrief)
            .filter(SalesBrief.company_id == company_id)
            .order_by(SalesBrief.created_at.desc())
            .first()
        )


__all__ = ["SalesBriefService"]
