"""Integração da geração de Prototype por IA com a fila RQ (Fase 9 /
Prompt 11) — mesmo padrão de `app.domains.{discovery,audit,briefing}.jobs`
desde a Fase 8.2: `enqueue_or_run_prototype_generation` tenta enfileirar
no RQ; se a fila estiver indisponível, executa de forma síncrona.

Diferente dos outros três domínios: o `GenerationRun` já existe (em
`PENDING`, criado por `PrototypeGenerationService.start()` na própria
rota HTTP, de forma síncrona) ANTES deste módulo ser chamado — o job
(`run_prototype_generation`) só executa `PrototypeGenerationService.
execute(run)`, nunca cria o `GenerationRun`. Isso é o que permite `GET
/api/prototypes/{id}/generations/{generation_id}` (seção 5 do Prompt 11)
responder algo coerente mesmo enquanto a geração real ainda não terminou
— o `id` já existe desde a resposta do `POST /generate`.

Por que enfileirar (decisão da seção 5, "síncrono ou assíncrono?"): uma
geração de árvore de componentes inteira pode demorar mais que uma
mensagem de Outreach — vale a pena não bloquear a requisição HTTP quando
um worker real e Redis estiverem disponíveis. Nesta máquina de
desenvolvimento (sem Redis), o efeito prático é idêntico ao síncrono —
mas o contrato da API já é o certo para quando essa infraestrutura
existir de verdade, sem precisar reescrever nada depois.

Sem retry automático: mesma decisão de cada outro domínio que chama IA —
um retry de job inteiro poderia duplicar uma chamada paga à Anthropic.
"""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.session import SessionLocal
from app.jobs.queue import bind_job_context, get_queue

logger = get_logger(__name__)

# Nome da fila lido por `app.worker` — precisa ser adicionado a
# `app.worker.DEFAULT_QUEUES` também, ou o worker nunca a consome (mesmo
# aviso já presente em cada `app/domains/*/jobs.py`).
QUEUE_NAME = "prototype_generation"


def run_prototype_generation(generation_run_id: str) -> None:
    """Corpo do job para execução em um processo separado (worker do RQ):
    abre sua própria sessão, busca o `GenerationRun` (já `PENDING`) e
    executa o trabalho real. Importável isoladamente por referência de
    módulo, como o RQ exige para serializar o job."""
    bind_job_context()
    from app.domains.prototypes.generation.service import PrototypeGenerationService
    from app.domains.prototypes.models import GenerationRun

    db = SessionLocal()
    try:
        run = db.get(GenerationRun, uuid.UUID(generation_run_id))
        if run is None:
            logger.warning("prototype_generation_job_run_not_found", generation_run_id=generation_run_id)
            return
        PrototypeGenerationService(db).execute(run)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def enqueue_or_run_prototype_generation(generation_run_id: uuid.UUID, *, db: Session | None = None) -> str:
    """Retorna `"queued"` quando o job foi enfileirado no Redis, ou
    `"executed_sync"` quando rodou no processo atual por fallback.

    Passe `db` quando chamado a partir de um handler HTTP que já tem uma
    sessão aberta com o `GenerationRun` recém-criado — evita abrir uma
    segunda conexão que não o enxergaria ainda não commitado na primeira
    (mesmo motivo de `app.domains.audit.jobs`).
    """
    try:
        queue = get_queue(QUEUE_NAME)
        queue.enqueue(run_prototype_generation, str(generation_run_id))
        return "queued"
    except Exception as exc:  # noqa: BLE001 - fila indisponível é um modo operacional válido aqui
        logger.warning(
            "prototype_generation_queue_unavailable_running_sync",
            generation_run_id=str(generation_run_id),
            error_type=exc.__class__.__name__,
        )
        if db is not None:
            from app.domains.prototypes.generation.service import PrototypeGenerationService
            from app.domains.prototypes.models import GenerationRun

            run = db.get(GenerationRun, generation_run_id)
            assert run is not None  # criado por PrototypeGenerationService.start() na mesma transação
            PrototypeGenerationService(db).execute(run)
        else:
            run_prototype_generation(str(generation_run_id))
        return "executed_sync"
