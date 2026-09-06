"""Orquestração do Digital Audit:

Company -> candidato de website -> validação SSRF -> busca segura ->
sinais HTML -> Evidence -> AuditSnapshot -> Website Quality Score.

`status` (`AuditStatus`) descreve se o PROCESSO da auditoria rodou com
sucesso; `site_state` (`DataState`) descreve o que foi ENCONTRADO sobre o
site. Um site inacessível, ambíguo ou bloqueado por política de SSRF é um
resultado válido de auditoria — `status=COMPLETED` mesmo assim.
`status=FAILED` fica reservado para erros verdadeiramente inesperados do
próprio processo (nunca para "o site não respondeu").
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import httpx
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.domains.audit.enums import AuditStatus
from app.domains.audit.html_signals import HtmlSignals, extract_html_signals
from app.domains.audit.http_client import FetchError, FetchResult, fetch_safely
from app.domains.audit.models import AuditSnapshot, WebsiteQuality
from app.domains.audit.scoring import compute_website_quality, is_html_content_type
from app.domains.audit.ssrf import ResolverFn, UnsafeURLError, default_resolve
from app.domains.audit.website_candidate import (
    WebsiteCandidate,
    WebsiteCandidateStatus,
    select_website_candidate,
)
from app.domains.companies.models import Company
from app.domains.evidence.enums import ConfidenceLevel, DataState, EvidenceMethod
from app.domains.evidence.queries import upsert_evidence

logger = get_logger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _decode_body(fetch: FetchResult) -> str:
    charset = "utf-8"
    if fetch.content_type and "charset=" in fetch.content_type:
        charset = fetch.content_type.split("charset=", 1)[1].split(";")[0].strip().strip('"')
    try:
        return fetch.body.decode(charset, errors="replace")
    except (LookupError, UnicodeDecodeError):
        return fetch.body.decode("utf-8", errors="replace")


class DigitalAuditService:
    def __init__(
        self,
        db: Session,
        *,
        settings: Settings | None = None,
        http_client: httpx.Client | None = None,
        resolver: ResolverFn = default_resolve,
    ) -> None:
        self._db = db
        self._settings = settings or get_settings()
        # Injetáveis só para testes (`httpx.Client(transport=httpx.MockTransport(...))`
        # e um resolver de DNS falso) — em produção, `fetch_safely` cria e fecha seu
        # próprio client por chamada, e a resolução de DNS é a real.
        self._http_client = http_client
        self._resolver = resolver

    # -- Ciclo de vida do AuditSnapshot --------------------------------------

    def start_audit(self, company_id: uuid.UUID) -> AuditSnapshot:
        company = self._db.get(Company, company_id)
        if company is None:
            raise ValueError(f"Company {company_id} não encontrada")

        snapshot = AuditSnapshot(company_id=company_id, run_id=uuid.uuid4(), status=AuditStatus.PENDING)
        self._db.add(snapshot)
        self._db.flush()
        return snapshot

    def execute(self, audit_snapshot_id: uuid.UUID) -> AuditSnapshot:
        snapshot = self._db.get(AuditSnapshot, audit_snapshot_id)
        if snapshot is None:
            raise ValueError(f"AuditSnapshot {audit_snapshot_id} não encontrado")

        snapshot.status = AuditStatus.RUNNING
        snapshot.started_at = _now()
        self._db.flush()

        try:
            return self._run(snapshot)
        except Exception as exc:  # noqa: BLE001 - falha inesperada nunca deve propagar como 500
            logger.error(
                "audit_failed_unexpectedly",
                company_id=str(snapshot.company_id),
                audit_snapshot_id=str(snapshot.id),
                error_type=exc.__class__.__name__,
                error=str(exc),
            )
            snapshot.status = AuditStatus.FAILED
            snapshot.error_code = exc.__class__.__name__
            snapshot.error_message = str(exc)[:500]
            snapshot.finished_at = _now()
            self._db.flush()
            return snapshot

    def _run(self, snapshot: AuditSnapshot) -> AuditSnapshot:
        candidate = select_website_candidate(self._db, snapshot.company_id)

        if candidate.status == WebsiteCandidateStatus.NONE:
            return self._finish(
                snapshot, site_state=DataState.NOT_DETECTED, website_url=None, fetch=None, html=None,
                note=candidate.note,
            )

        if candidate.status == WebsiteCandidateStatus.AMBIGUOUS:
            return self._finish(
                snapshot, site_state=DataState.INCONCLUSIVE, website_url=candidate.url, fetch=None, html=None,
                note=candidate.note,
            )

        try:
            fetch = fetch_safely(
                candidate.url, settings=self._settings, client=self._http_client, resolver=self._resolver
            )
        except UnsafeURLError as exc:
            logger.warning(
                "audit_url_blocked_by_ssrf",
                company_id=str(snapshot.company_id),
                url=candidate.url,
                reason=exc.reason,
            )
            return self._finish(
                snapshot, site_state=DataState.NOT_CHECKED, website_url=candidate.url, fetch=None, html=None,
                note=f"bloqueado por política de segurança (SSRF): {exc.reason}",
            )
        except FetchError as exc:
            return self._finish(
                snapshot, site_state=DataState.INACCESSIBLE, website_url=candidate.url, fetch=None, html=None,
                note=f"{exc.reason}: {exc}",
            )

        html_signals: HtmlSignals | None = None
        if is_html_content_type(fetch.content_type) and fetch.body:
            try:
                html_signals = extract_html_signals(_decode_body(fetch), base_url=fetch.final_url)
            except Exception as exc:  # noqa: BLE001 - HTML de terceiro nunca pode derrubar a auditoria
                logger.warning(
                    "audit_html_parse_failed", company_id=str(snapshot.company_id), error=str(exc)
                )

        self._record_evidence(snapshot, candidate, fetch, html_signals)

        return self._finish(
            snapshot, site_state=DataState.CONFIRMED, website_url=fetch.final_url, fetch=fetch, html=html_signals,
        )

    # -- Evidence -------------------------------------------------------------

    def _record_evidence(
        self,
        snapshot: AuditSnapshot,
        candidate: WebsiteCandidate,
        fetch: FetchResult,
        html: HtmlSignals | None,
    ) -> None:
        source = candidate.source or "digital_audit"
        structured = dict(
            company_id=snapshot.company_id,
            source=source,
            method=EvidenceMethod.STRUCTURED_FIELD,
            confidence=ConfidenceLevel.HIGH,
            audit_snapshot_id=snapshot.id,
            source_url=fetch.final_url,
        )

        upsert_evidence(self._db, field="website_accessible", value=fetch.final_url, state=DataState.CONFIRMED, **structured)
        upsert_evidence(
            self._db, field="website_https", value="true" if fetch.is_https else "false",
            state=DataState.CONFIRMED, **structured,
        )
        upsert_evidence(
            self._db, field="website_status_code", value=str(fetch.status_code), state=DataState.CONFIRMED,
            **structured,
        )

        if html is None:
            return

        heuristic = dict(
            company_id=snapshot.company_id,
            source=source,
            method=EvidenceMethod.HEURISTIC_MATCH,
            confidence=ConfidenceLevel.MEDIUM,
            audit_snapshot_id=snapshot.id,
            source_url=fetch.final_url,
        )

        if html.title:
            upsert_evidence(self._db, field="website_title", value=html.title[:2048], state=DataState.CONFIRMED, **heuristic)
        if html.meta_description:
            upsert_evidence(
                self._db, field="website_meta_description", value=html.meta_description[:2048],
                state=DataState.CONFIRMED, **heuristic,
            )
        if html.phone_like_text_found or html.contact_link_found:
            upsert_evidence(
                self._db, field="website_contact_available", value="true", state=DataState.CONFIRMED, **heuristic
            )
        if html.social_links:
            upsert_evidence(
                self._db, field="website_social_links", value=", ".join(html.social_links[:10]),
                state=DataState.CONFIRMED, **heuristic,
            )

    # -- Finalização ------------------------------------------------------------

    def _finish(
        self,
        snapshot: AuditSnapshot,
        *,
        site_state: DataState,
        website_url: str | None,
        fetch: FetchResult | None,
        html: HtmlSignals | None,
        note: str | None = None,
    ) -> AuditSnapshot:
        quality_result = compute_website_quality(site_state=site_state, fetch=fetch, html=html)

        snapshot.site_state = site_state
        snapshot.website_url = website_url
        snapshot.status = AuditStatus.COMPLETED
        snapshot.finished_at = _now()
        if note:
            snapshot.error_message = note[:500]

        quality = WebsiteQuality(
            audit_snapshot_id=snapshot.id,
            score=quality_result.score,
            components=quality_result.components or None,
            signals=quality_result.signals or None,
            confidence=quality_result.confidence,
            limitations=quality_result.limitations or None,
        )
        self._db.add(quality)
        self._db.flush()

        logger.info(
            "audit_completed",
            company_id=str(snapshot.company_id),
            audit_snapshot_id=str(snapshot.id),
            site_state=site_state.value,
            score=quality_result.score,
        )
        return snapshot


__all__ = ["DigitalAuditService"]
