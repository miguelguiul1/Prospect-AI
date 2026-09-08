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

**Refinamento por linguagem natural (Prompt 12)**: `start()`/`execute()`
agora servem os dois casos — geração inicial (`instruction=None`) e
refinamento (`instruction` preenchido) — com o MESMO pipeline de
validação (`validate_generated_tree`/`find_grounding_warnings`, camada
única, nunca duplicada) e o mesmo tratamento de falha. A única diferença
real está em `execute()`: qual função de `generation.prompt` monta o
prompt, e se uma `PrototypeVersion` resultante grava `diff_summary`
(só para refinamento — geração inicial não tem "antes" para comparar).

**Reaproveitar ou renovar o contexto no refinamento?** Decisão: SEMPRE
renovar (`PrototypeContextBuilder(self._db).build(...)` roda de novo, sem
nenhum atalho para reaproveitar o `ContextSnapshot` de uma geração
anterior) — mesmo caminho de código da geração inicial, sem nenhum `if`
extra. Isso diverge da expectativa original da auditoria (seção 25,
citada no Prompt 12: "a expectativa é reaproveitar o contexto existente
[...] para evitar regenerar tudo do zero"), e a divergência é
deliberada: `PrototypeContextBuilder.build()` é uma consulta ao PRÓPRIO
banco (Company/Evidence/AuditSnapshot/OpportunityScore/SalesBrief) — zero
custo de IA, zero chamada de rede paga. O único custo real de um
refinamento é a chamada ao provider de IA, que acontece de qualquer forma
independente de reaproveitar ou renovar o contexto. Ou seja: o motivo
original para "reaproveitar" (economizar) não se aplica aqui — renovar é
estritamente melhor (contexto sempre atualizado, caso a Evidence tenha
mudado desde a última geração) pelo mesmo custo. Reaproveitar só faria
sentido se o Context Builder em si fosse caro, o que nunca foi o caso.
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
from app.domains.prototypes.generation.diffing import summarize_component_diff
from app.domains.prototypes.generation.prompt import PROMPT_VERSION, build_prompt, build_refinement_prompt
from app.domains.prototypes.generation.validation import find_grounding_warnings, validate_generated_tree
from app.domains.prototypes.models import ContextSnapshot, GenerationRun, GenerationStatus, Prototype, PrototypeVersion
from app.domains.prototypes.versioning import create_version

logger = get_logger(__name__)

_METRIC_DOMAIN = "prototype_generation"


def _now() -> datetime:
    return datetime.now(timezone.utc)


class GenerationInProgressError(ValueError):
    """Já existe uma execução `PENDING` para este `Prototype` (seção 5 do
    Prompt 11 — no máximo uma geração em andamento por vez)."""


class NoPreviousVersionError(ValueError):
    """Refinamento pedido para um `Prototype` que ainda não tem NENHUM
    `GenerationRun` bem-sucedido (definição da seção 1 do Prompt 12: um
    refinamento só existe "sobre um Prototype que já tem pelo menos uma
    geração bem-sucedida"). Nunca cai silenciosamente para uma geração do
    zero — isso seria surpreendente (o usuário pediu para MUDAR algo que,
    do ponto de vista dele, já existe)."""


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

    def start(self, prototype: Prototype, *, instruction: str | None = None) -> GenerationRun:
        """Cria o `GenerationRun` em `PENDING` e retorna — nunca chama o
        provider aqui. Rápido e síncrono de propósito: é o que a rota
        `POST /generate`/`POST /refine` devolve no corpo da resposta 202.

        `instruction=None` → geração inicial (comportamento inalterado do
        Prompt 11). `instruction` preenchido → refinamento (Prompt 12):
        exige que o `Prototype` já tenha pelo menos um `GenerationRun`
        `SUCCEEDED` (`NoPreviousVersionError` se não), e registra
        `based_on_version_number` = a versão mais recente NESTE momento,
        só para auditoria (ver docstring do módulo sobre o que de fato é
        enviado ao provider)."""
        self.validate_preconditions(prototype)
        assert prototype.company_id is not None  # garantido por PrototypeService.create (Prompt 10)

        based_on_version_number = None
        if instruction is not None:
            has_previous_success = (
                self._db.query(GenerationRun)
                .filter(
                    GenerationRun.prototype_id == prototype.id,
                    GenerationRun.status == GenerationStatus.SUCCEEDED,
                )
                .first()
                is not None
            )
            if not has_previous_success:
                raise NoPreviousVersionError(
                    f"O protótipo {prototype.id} ainda não tem nenhuma geração bem-sucedida — "
                    "refinamento exige um protótipo já gerado. Rode POST /generate primeiro."
                )
            latest_version = (
                self._db.query(PrototypeVersion)
                .filter(PrototypeVersion.prototype_id == prototype.id)
                .order_by(PrototypeVersion.version_number.desc())
                .first()
            )
            based_on_version_number = latest_version.version_number if latest_version is not None else None

        run = GenerationRun(
            prototype_id=prototype.id,
            company_id=prototype.company_id,
            status=GenerationStatus.PENDING,
            prompt_version=PROMPT_VERSION,
            context_version="pending",
            instruction=instruction,
            based_on_version_number=based_on_version_number,
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

        # Tree "antes", capturada ANTES de qualquer chamada ao provider —
        # é o que `find`/`diffing` comparam contra o resultado, e é sempre
        # `Prototype.components` (nunca o `components` da última
        # `PrototypeVersion` — ver docstring do módulo e de
        # `PrototypeVersion` sobre por que isso importa).
        components_before = prototype.components
        is_refinement = run.instruction is not None
        prompt = (
            build_refinement_prompt(context, current_components=components_before, instruction=run.instruction)
            if is_refinement
            else build_prompt(context)
        )
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
                # Achado real (Prompt 11): a chamada HTTP já teve sucesso
                # e provavelmente já foi cobrada pelo provider quando o
                # código chega aqui — só o CONTEÚDO falhou depois. Sem
                # capturar os tokens aqui, uma falha de parsing/validação
                # custava dinheiro real sem deixar nenhum registro de
                # quanto, quebrando o objetivo de custo do F8 ("identificar
                # toda operação que chama IA: tokens, custo").
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                duration_ms=response.duration_ms,
                error_code=exc.__class__.__name__,
                error_message=str(exc)[:500],
            )

        warnings = find_grounding_warnings(validated, context)
        components_after = [node.model_dump() for node in validated]

        run.status = GenerationStatus.SUCCEEDED
        run.provider = getattr(provider, "name", None)
        run.model = response.model
        run.context_version = context.context_version
        run.input_tokens = response.input_tokens
        run.output_tokens = response.output_tokens
        run.duration_ms = response.duration_ms
        run.grounding_warnings = warnings or None
        # Só para refinamento — a geração inicial não tem "antes" real
        # para comparar (a árvore anterior estaria sempre vazia, e um
        # diff contra vazio não mede nada útil).
        run.diff_summary = summarize_component_diff(components_before, components_after) if is_refinement else None
        run.completed_at = _now()
        self._db.add(ContextSnapshot(generation_run_id=run.id, context=context.to_dict()))

        create_version(self._db, prototype, components=components_after, generation_run_id=run.id)

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

    def generate(self, prototype: Prototype, *, instruction: str | None = None) -> GenerationRun:
        """Atalho síncrono: `start()` + `execute()` em sequência — usado
        pelo fallback sem Redis e por toda a suíte de testes desta fase
        (o provider fake responde instantaneamente, então não há
        diferença observável entre isto e o caminho enfileirado real).
        `instruction` repassado direto para `start()` — ver lá para a
        distinção geração inicial vs. refinamento."""
        run = self.start(prototype, instruction=instruction)
        return self.execute(run)

    def _parse_and_validate(self, raw_text: str) -> list:
        from app.core.ai_text import strip_markdown_code_fence

        payload = json.loads(strip_markdown_code_fence(raw_text))
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
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        duration_ms: float | None = None,
        error_code: str,
        error_message: str,
    ) -> GenerationRun:
        run.status = GenerationStatus.FAILED
        run.provider = provider_name
        run.model = model
        run.context_version = context.context_version if context is not None else "unknown"
        # `input_tokens`/`output_tokens` só vêm preenchidos quando a
        # chamada HTTP já teve sucesso e falhou depois (parsing/validação)
        # — nesse caso o provider já cobrou pela chamada, e perder esse
        # registro quebraria o rastreamento de custo real de IA (achado do
        # Prompt 11, ver docstring de onde este método é chamado).
        run.input_tokens = input_tokens
        run.output_tokens = output_tokens
        run.duration_ms = duration_ms
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
        if input_tokens is not None:
            metrics.increment("ai_tokens_total", {"domain": _METRIC_DOMAIN, "direction": "input"}, input_tokens)
        if output_tokens is not None:
            metrics.increment("ai_tokens_total", {"domain": _METRIC_DOMAIN, "direction": "output"}, output_tokens)
        return run

    def get(self, prototype_id: uuid.UUID, generation_id: uuid.UUID) -> GenerationRun | None:
        return (
            self._db.query(GenerationRun)
            .filter(GenerationRun.id == generation_id, GenerationRun.prototype_id == prototype_id)
            .first()
        )


__all__ = ["PrototypeGenerationService", "GenerationInProgressError", "NoPreviousVersionError"]
