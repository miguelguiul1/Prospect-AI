"""Abstrações de job para o processamento assíncrono futuro.

Nenhum worker concreto (Discovery, Digital Audit, Opportunity Scorer, Sales
Brief) é implementado nesta fase — apenas o contrato que eles vão seguir, e
a estrutura de correlação de execução usada pela observabilidade
(arquitetura v0.2, seção 20).
"""
from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, ClassVar


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class JobContext:
    """Identificadores de correlação propagados durante a execução de um job.

    `job_id` identifica esta execução específica; `run_id` correlaciona
    vários jobs que pertencem à mesma operação de negócio (ex.: todos os
    jobs de um mesmo `SearchRun` ou de um mesmo ciclo de auditoria);
    `correlation_id` é o identificador de mais alto nível, propagável até a
    requisição HTTP que disparou o job (ver `app.core.middleware`).
    """

    job_id: uuid.UUID = field(default_factory=uuid.uuid4)
    run_id: uuid.UUID | None = None
    correlation_id: str | None = None
    created_at: datetime = field(default_factory=_now)


class Job(ABC):
    """Contrato base para jobs assíncronos futuros.

    Implementações concretas (ex.: um job de Discovery ou de Digital Audit)
    pertencem às fases 1 a 4 e não existem nesta fase.
    """

    name: ClassVar[str]
    max_retries: ClassVar[int] = 3

    @abstractmethod
    def run(self, context: JobContext, **kwargs: Any) -> None:
        raise NotImplementedError
