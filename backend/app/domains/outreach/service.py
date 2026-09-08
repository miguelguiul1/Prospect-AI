"""Orquestração do Assisted Outreach (Fase 7):

Opportunity + Contact (opcional) -> Company/Score/Website Quality/Sales
Brief (via `app.domains.companies.queries.get_company_detail`, Fase 5,
reaproveitado sem duplicação) -> OutreachPromptContext -> prompt -> provider
de IA (o MESMO `AnthropicProvider` do Sales Brief, Fase 4) -> validação
(`OutreachContent`) -> `Outreach` persistido com `status=DRAFT`.

Uma resposta inválida do provider NUNCA vira um rascunho salvo (Prompt 11,
seção 19.3) — a exceção sobe para a rota, que responde com um erro
controlado e permite nova tentativa (nenhum retry automático, mesma
política do Sales Brief).
"""
from __future__ import annotations

import json
import uuid

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core import metrics
from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.domains.briefing.providers import get_provider
from app.domains.briefing.providers.base import SalesBriefProvider
from app.domains.briefing.providers.errors import ProviderInvalidResponseError, SalesBriefProviderError
from app.domains.companies.queries import get_company_detail
from app.domains.crm.models import Contact, Opportunity
from app.domains.crm.service import log_activity
from app.domains.crm.enums import ActivityType
from app.domains.evidence.queries import get_current_value
from app.domains.outreach.enums import OutreachChannel, OutreachStatus
from app.domains.outreach.models import Outreach
from app.domains.outreach.prompt import PROMPT_VERSION, OutreachPromptContext, build_prompt
from app.domains.outreach.schemas import OutreachContent

logger = get_logger(__name__)

_EVIDENCE_FIELDS = ["website_title", "website_meta_description", "website_social_links"]

_ALLOWED_TRANSITIONS: dict[OutreachStatus, set[str]] = {
    OutreachStatus.DRAFT: {"mark_ready", "mark_sent", "cancel"},
    OutreachStatus.READY: {"mark_sent", "cancel"},
    OutreachStatus.SENT_MANUALLY: set(),
    OutreachStatus.CANCELLED: set(),
}


class OutreachGenerationError(Exception):
    """A geração de IA falhou (provider indisponível/timeout/resposta
    inválida) — nunca vira um rascunho salvo. A rota converte isto em um
    erro HTTP controlado, nunca um 500 nem um outreach fabricado."""


class OutreachService:
    def __init__(self, db: Session, *, settings: Settings | None = None, provider: SalesBriefProvider | None = None) -> None:
        self._db = db
        self._settings = settings or get_settings()
        self._provider = provider

    def build_context(self, opportunity: Opportunity, contact: Contact | None) -> OutreachPromptContext:
        detail = get_company_detail(self._db, opportunity.company_id)
        assert detail is not None

        audit = detail.latest_audit
        quality = detail.latest_website_quality
        score = detail.latest_score
        brief = detail.latest_brief
        brief_content = brief.content if brief and brief.status.value == "completed" else None

        evidence = {field: get_current_value(self._db, opportunity.company_id, field) for field in _EVIDENCE_FIELDS}

        return OutreachPromptContext(
            company_name=detail.company.canonical_name,
            category=detail.company.category.name if detail.company.category else None,
            region=detail.company.region.name if detail.company.region else None,
            channel="",  # preenchido em generate_draft (depende do parâmetro do usuário)
            site_state=audit.site_state.value if audit and audit.site_state else "desconhecido",
            website_quality_score=quality.score if quality else None,
            opportunity_tier=score.tier.value if score and score.tier else None,
            sales_brief_summary=(brief_content or {}).get("summary"),
            sales_brief_suggested_angle=(brief_content or {}).get("suggested_angle"),
            sales_brief_digital_gaps=(brief_content or {}).get("digital_gaps"),
            # Só personaliza com nome/cargo se o contato existir E já tiver
            # sido validado por um humano — nunca a partir de um contato
            # "unverified" (Prompt 11, seção 19: "a IA NÃO pode inventar
            # fatos"; auditoria F7.0, ADR-007).
            contact_name=contact.name if contact and contact.validation_status.value == "verified" else None,
            contact_role=contact.role if contact and contact.validation_status.value == "verified" else None,
            evidence=evidence,
        )

    def generate_draft(
        self, opportunity: Opportunity, *, contact: Contact | None, channel: OutreachChannel, user_id: uuid.UUID
    ) -> Outreach:
        context = self.build_context(opportunity, contact)
        context = OutreachPromptContext(**{**context.__dict__, "channel": channel.value})
        prompt = build_prompt(context)
        provider = self._provider or get_provider(self._settings)

        try:
            response = provider.generate(
                system=prompt["system"], user=prompt["user"], max_tokens=self._settings.outreach_max_tokens
            )
            content = self._validate_content(response.content)
        except SalesBriefProviderError as exc:
            logger.warning(
                "outreach_generation_failed",
                opportunity_id=str(opportunity.id),
                error_code=exc.__class__.__name__,
            )
            metrics.increment("ai_requests_total", {"domain": "outreach", "status": "failed"})
            raise OutreachGenerationError(str(exc)) from exc

        outreach = Outreach(
            opportunity_id=opportunity.id,
            contact_id=contact.id if contact else None,
            channel=channel,
            status=OutreachStatus.DRAFT,
            subject=content.subject,
            message=content.message,
            rationale=content.rationale,
            evidence_ids=content.evidence_ids,
            generated_by_ai=True,
            provider=getattr(provider, "name", None),
            model=response.model,
            prompt_version=PROMPT_VERSION,
            duration_ms=response.duration_ms,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            created_by=user_id,
        )
        self._db.add(outreach)
        self._db.flush()

        log_activity(
            self._db,
            opportunity_id=opportunity.id,
            type_=ActivityType.OUTREACH,
            created_by=user_id,
            title=f"Rascunho de outreach gerado ({channel.value})",
            context={"outreach_id": str(outreach.id)},
        )

        logger.info(
            "outreach_draft_generated",
            opportunity_id=str(opportunity.id),
            outreach_id=str(outreach.id),
            provider=outreach.provider,
        )
        metrics.increment("ai_requests_total", {"domain": "outreach", "status": "completed"})
        if outreach.input_tokens is not None:
            metrics.increment("ai_tokens_total", {"domain": "outreach", "direction": "input"}, outreach.input_tokens)
        if outreach.output_tokens is not None:
            metrics.increment("ai_tokens_total", {"domain": "outreach", "direction": "output"}, outreach.output_tokens)
        return outreach

    def _validate_content(self, raw_text: str) -> OutreachContent:
        from app.core.ai_text import strip_markdown_code_fence

        try:
            payload = json.loads(strip_markdown_code_fence(raw_text))
        except json.JSONDecodeError as exc:
            raise ProviderInvalidResponseError(f"Resposta do provider não é JSON válido: {exc}") from exc
        try:
            return OutreachContent.model_validate(payload)
        except ValidationError as exc:
            raise ProviderInvalidResponseError(f"Resposta do provider não validou contra o schema esperado: {exc}") from exc

    def edit(self, outreach: Outreach, *, subject: str | None, message: str | None) -> Outreach:
        if outreach.status not in {OutreachStatus.DRAFT, OutreachStatus.READY}:
            raise ValueError("Só é possível editar um outreach em rascunho ou pronto para envio.")
        if subject is not None:
            outreach.subject = subject
        if message is not None:
            outreach.message = message
        self._db.flush()
        return outreach

    def transition(self, outreach: Outreach, *, action: str, user_id: uuid.UUID) -> Outreach:
        allowed = _ALLOWED_TRANSITIONS.get(outreach.status, set())
        if action not in allowed:
            raise ValueError(
                f"Não é possível aplicar '{action}' a um outreach com status '{outreach.status.value}'."
            )

        if action == "mark_ready":
            outreach.status = OutreachStatus.READY
        elif action == "cancel":
            outreach.status = OutreachStatus.CANCELLED
        elif action == "mark_sent":
            # ÚNICA transição que representa um envio real — sempre uma
            # confirmação explícita do usuário, nunca automática (Prompt 11,
            # seção 18.2).
            outreach.status = OutreachStatus.SENT_MANUALLY
            log_activity(
                self._db,
                opportunity_id=outreach.opportunity_id,
                type_=ActivityType.OUTREACH,
                created_by=user_id,
                title=f"Mensagem enviada manualmente ({outreach.channel.value})",
                context={"outreach_id": str(outreach.id)},
            )
        self._db.flush()
        return outreach

    def list_for_opportunity(self, opportunity_id: uuid.UUID) -> list[Outreach]:
        return (
            self._db.query(Outreach)
            .filter(Outreach.opportunity_id == opportunity_id)
            .order_by(Outreach.created_at.desc())
            .all()
        )


__all__ = ["OutreachService", "OutreachGenerationError"]
