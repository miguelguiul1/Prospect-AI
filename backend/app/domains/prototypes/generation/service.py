"""Orquestração da geração de Prototype por IA (Fase 9 / Prompt 11):

PrototypeContext -> prompt -> provider de IA -> Component Tree (JSON) ->
validação -> `GenerationRun` + `ContextSnapshot` persistidos ->
`Prototype.components` atualizado.

Dividido em duas etapas deliberadamente (`start`/`execute`), não uma só
(`generate`, que compõe as duas para o caso síncrono/testes):

- `start(prototype)`: síncrono, rápido, chamado sempre pela rota HTTP
  ANTES de enfileirar/executar a chamada real ao provider. Cria o
  `GenerationRun` já em `PENDING` e retorna imediatamente — é esse `id`
  que a rota devolve na resposta 202 e que `GET /generations/{id}`
  (seção 5 do Prompt 11) consulta enquanto a geração real ainda não
  terminou. Levanta `GenerationInProgressError` se já existe um `PENDING`
  para este `Prototype` (no máximo uma geração em andamento por vez).
- `execute(run)`: o trabalho pesado (contexto -> prompt -> provider ->
  validação -> persistência). Atualiza o `GenerationRun` já existente no
  lugar — nunca cria uma segunda linha. Chamado tanto pelo fallback
  síncrono (`app.domains.prototypes.jobs.enqueue_or_run_prototype_generation`,
  mesmo processo/sessão da requisição) quanto por um worker RQ real
  (processo separado, sua própria sessão) — o mesmo método serve os dois
  casos porque nenhum dos dois sabe nem precisa saber COMO foi disparado.

Mesma regra de todo domínio que chama IA neste projeto desde a Fase 4:
falha do provider, JSON malformado ou conteúdo inseguro NUNCA vira um
protótipo vazio nem um `GenerationRun` inventado — sempre um
`GenerationRun.status=FAILED` com o motivo registrado. Sem retry
automático (mesma decisão do Sales Brief, pelo mesmo motivo: uma
chamada de IA já é cara o suficiente; um retry de job inteiro poderia
duplicar o custo sem necessidade).
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core import metrics
from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.domains.prototypes.context import InsufficientContextError, PrototypeContext, PrototypeContextBuilder
from app.domains.prototypes.generation import get_generation_provider
from app.domains.prototypes.generation.base import GenerationProvider, GenerationProviderError
from app.domains.prototypes.generation.prompt import PROMPT_VERSION, build_prompt
from app.domains.prototypes.generation.validation import find_grounding_warnings, validate_generated_tree
from app.domains.prototypes.models import ContextSnapshot, GenerationRun, GenerationStatus, Prototype

logger = get_logger(__name__)

_METRIC_DOMAIN = "prototype_generation"


def _now() -> datetime:
    return datetime.now(timezone.utc)


class GenerationInProgressError(ValueError):
    """Já existe uma execução `PENDING` para este `Prototype` (seção 5 do
    Prompt 11 — no máximo uma geração em andamento por vez)."""


class PrototypeGenerationService:
    def __init__(
        self,
        db: Session,
        *,
        settings: Settings | None = None,
        provider: GenerationProvider | None = None,
    ) -> None:
        self._db = db
        self._settings = settings or get_settings()
        # Injetável só para testes (um provider falso) — em produção,
        # `get_generation_provider` decide a implementação real.
        self._provider = provider

    def validate_preconditions(self, prototype: Prototype) -> None:
        """Levanta `GenerationInProgressError` se já existe uma execução
        `PENDING` para este `Prototype` — checagem síncrona ANTES de
        criar uma nova execução, nunca descoberta só depois (mesmo
        espírito de `SalesBriefService.validate_preconditions`)."""
        pending = (
            self._db.query(GenerationRun)
            .filter(GenerationRun.prototype_id == prototype.id, GenerationRun.status == GenerationStatus.PENDING)
            .first()
        )
        if pending is not None:
            raise GenerationInProgressError(
                f"Já existe uma geração em andamento para o protótipo {prototype.id} (iniciada em "
                f"{pending.created_at.isoformat()}) — aguarde ela terminar antes de gerar novamente."
            )

    def start(self, prototype: Prototype) -> GenerationRun:
        """Cria o `GenerationRun` em `PENDING` e retorna — nunca chama o
        provider aqui. Rápido e síncrono de propósito: é o que a rota
        `POST /generate` devolve no corpo da resposta 202."""
        self.validate_preconditions(prototype)
        assert prototype.company_id is not None  # garantido por PrototypeService.create (Prompt 10)

        run = GenerationRun(
            prototype_id=prototype.id,
            company_id=prototype.company_id,
            status=GenerationStatus.PENDING,
            prompt_version=PROMPT_VERSION,
            context_version="pending",
        )
        self._db.add(run)
        self._db.flush()
        return run

    def execute(self, run: GenerationRun) -> GenerationRun:
        """O trabalho real. Atualiza `run` (já `PENDING`) no lugar para
        `SUCCEEDED` ou `FAILED` — nunca cria uma segunda linha."""
        prototype = self._db.get(Prototype, run.prototype_id)
        assert prototype is not None  # a FK garante isto; só None se alguém apagou o Prototype no meio do caminho

        try:
            context = PrototypeContextBuilder(self._db).build(run.company_id)
        except InsufficientContextError as exc:
            return self._fail(run, error_code=exc.__class__.__name__, error_message=str(exc)[:500])

        prompt = build_prompt(context)
        provider = self._provider or get_generation_provider(self._settings)

        try:
            response = provider.generate(
                system=prompt["system"],
                user=prompt["user"],
                max_tokens=self._settings.prototype_generation_max_tokens,
            )
            validated = self._parse_and_validate(response.content)
        except GenerationProviderError as exc:
            return self._fail(
                run,
                context=context,
                provider_name=getattr(provider, "name", None),
                error_code=exc.__class__.__name__,
                error_message=str(exc)[:500],
            )
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            # JSON malformado, chave "components" ausente, ou falha de
            # validação (catálogo/estrutura/URL insegura) — nunca um
            # protótipo parcialmente aplicado. `response` sempre está
            # definida aqui: só se chega a este `except` depois de
            # `provider.generate()` já ter retornado com sucesso.
            return self._fail(
                run,
                context=context,
                provider_name=getattr(provider, "name", None),
                model=response.model,
                error_code=exc.__class__.__name__,
                error_message=str(exc)[:500],
            )

        warnings = find_grounding_warnings(validated, context)

        run.status = GenerationStatus.SUCCEEDED
        run.provider = getattr(provider, "name", None)
        run.model = response.model
        run.context_version = context.context_version
        run.input_tokens = response.input_tokens
        run.output_tokens = response.output_tokens
        run.duration_ms = response.duration_ms
        run.grounding_warnings = warnings or None
        run.completed_at = _now()
        self._db.add(ContextSnapshot(generation_run_id=run.id, context=context.to_dict()))

        prototype.components = [node.model_dump() for node in validated]
        self._db.flush()

        logger.info(
            "prototype_generation_succeeded",
            prototype_id=str(prototype.id),
            company_id=str(run.company_id),
            generation_run_id=str(run.id),
            provider=run.provider,
            model=run.model,
            component_count=len(validated),
            grounding_warning_count=len(warnings),
        )
        metrics.increment("ai_requests_total", {"domain": _METRIC_DOMAIN, "status": "completed"})
        if run.input_tokens is not None:
            metrics.increment("ai_tokens_total", {"domain": _METRIC_DOMAIN, "direction": "input"}, run.input_tokens)
        if run.output_tokens is not None:
            metrics.increment("ai_tokens_total", {"domain": _METRIC_DOMAIN, "direction": "output"}, run.output_tokens)
        return run

    def generate(self, prototype: Prototype) -> GenerationRun:
        """Atalho síncrono: `start()` + `execute()` em sequência — usado
        pelo fallback sem Redis e por toda a suíte de testes desta fase
        (o provider fake responde instantaneamente, então não há
        diferença observável entre isto e o caminho enfileirado real)."""
        run = self.start(prototype)
        return self.execute(run)

    def _parse_and_validate(self, raw_text: str) -> list:
        payload = json.loads(raw_text)
        components = payload["components"]
        if not isinstance(components, list):
            raise TypeError("campo 'components' da resposta do provider não é uma lista")
        return validate_generated_tree(components)

    def _fail(
        self,
        run: GenerationRun,
        *,
        context: PrototypeContext | None = None,
        provider_name: str | None = None,
        model: str | None = None,
        error_code: str,
        error_message: str,
    ) -> GenerationRun:
        run.status = GenerationStatus.FAILED
        run.provider = provider_name
        run.model = model
        run.context_version = context.context_version if context is not None else "unknown"
        run.error_code = error_code
        run.error_message = error_message
        run.completed_at = _now()

        if context is not None:
            # Mesmo numa falha, saber QUAL contexto foi tentado ajuda a
            # diagnosticar depois (ex.: "o contexto era bom, foi só o
            # provider que falhou" vs. "o contexto já era pobre demais").
            self._db.add(ContextSnapshot(generation_run_id=run.id, context=context.to_dict()))

        self._db.flush()

        logger.warning(
            "prototype_generation_failed",
            prototype_id=str(run.prototype_id),
            company_id=str(run.company_id),
            generation_run_id=str(run.id),
            error_code=error_code,
        )
        metrics.increment("ai_requests_total", {"domain": _METRIC_DOMAIN, "status": "failed"})
        return run

    def get(self, prototype_id: uuid.UUID, generation_id: uuid.UUID) -> GenerationRun | None:
        return (
            self._db.query(GenerationRun)
            .filter(GenerationRun.id == generation_id, GenerationRun.prototype_id == prototype_id)
            .first()
        )


__all__ = ["PrototypeGenerationService", "GenerationInProgressError"]
