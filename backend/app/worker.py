"""Entrypoint do worker RQ real (Fase 8.2).

Antes desta fase, nenhum processo consumia as filas Redis (`discovery`,
`audit`, `briefing`) — mesmo com Redis disponível, um job "enfileirado"
ficaria parado para sempre, porque nenhum worker jamais existiu no projeto
(achado da auditoria F8.0, seção 10). Este módulo é o processo que resolve
isso.

Uso:
    python -m app.worker                    # as três filas reais do projeto
    python -m app.worker discovery audit     # subconjunto específico

Não retenta jobs automaticamente por padrão — cada domínio já decidiu
deliberadamente não reexecutar (retries de rede já acontecem dentro do
provider/`fetch_safely`; um retry de job inteiro poderia duplicar uma
chamada paga à Anthropic/Google, ver os comentários em cada
`app/domains/*/jobs.py`). Se algum job precisar de retry no futuro, isso
deve ser configurado explicitamente em `queue.enqueue(..., retry=Retry(...))`
no ponto de enfileiramento, não neste worker.

Shutdown gracioso: o `Worker.work()` da própria biblioteca RQ já trata
SIGINT/SIGTERM nativamente — um primeiro sinal (Ctrl+C) pede para o job
atual terminar antes de sair (warm shutdown); um segundo sinal força saída
imediata (cold shutdown). Nenhum tratamento de sinal próprio é adicionado
aqui, para não sobrescrever esse comportamento já correto da biblioteca.

**`Worker` no Windows (achado real, não hipotético)**: a `rq.Worker`
padrão isola cada job num processo filho via `os.fork()` — que não existe
no Windows (`AttributeError: module 'os' has no attribute 'fork'`,
observado ao rodar este módulo pela primeira vez contra Redis real nesta
sessão; nenhuma sessão anterior tinha Redis real disponível pra expor
isso). Sem fork, o worker inteiro morre ao pegar o PRIMEIRO job — nunca
foi um problema hipotético de compatibilidade, é o comportamento real
observado. `rq.SimpleWorker` executa o job no mesmo processo, sem fork
(mesma classe que `tests/infra/test_real_worker.py` já usa, pelo mesmo
motivo). Usar `SimpleWorker` só no Windows preserva o isolamento por
processo (um job que trava/estoura memória não derruba o worker inteiro)
em produção real (Linux), onde `os.fork()` existe e funciona.

**Por que a seleção é uma função pura (`_select_worker_class`), não só uma
expressão em linha**: a primeira versão testava isto via subprocesso com
`sys.platform` sobrescrito ANTES do `import rq` — quebrou no CI (Linux)
com `ModuleNotFoundError: No module named '_overlapped'`, porque
`sys.platform` é só uma string que o NOSSO código lê; o `asyncio` da
biblioteca padrão decide `windows_events` vs `unix_events` pelo SO real
por outro caminho, e `_overlapped` (um módulo compilado) só existe numa
build real do Python para Windows — enganar `sys.platform` engana este
módulo, mas não engana `asyncio` nem qualquer outra dependência com sua
própria detecção de plataforma. Isolar a decisão numa função pura permite
testar as duas branches sem nunca importar `rq` sob uma plataforma
forjada — `rq` (e tudo que ele importa) é sempre importado uma única vez,
contra o SO real de verdade, não importa qual `platform` a função recebe
como argumento depois.
"""
from __future__ import annotations

import sys

from rq import SimpleWorker, Worker

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.jobs.queue import get_redis_connection


def _select_worker_class(platform: str) -> type[SimpleWorker] | type[Worker]:
    """Decisão pura sobre STRINGS já conhecidas (`SimpleWorker`/`Worker`
    já foram importados de verdade contra o SO real antes desta função
    ser chamada) — ver docstring do módulo para o porquê disto importar
    para como este código é testado."""
    return SimpleWorker if platform == "win32" else Worker


# Ver docstring do módulo — `os.fork()` não existe no Windows, então a
# `Worker` padrão (baseada em fork) crasha ao executar o primeiro job
# nessa plataforma.
_WorkerClass = _select_worker_class(sys.platform)

# Sincronizado manualmente com `QUEUE_NAME` em cada
# `app/domains/{discovery,audit,briefing,prototypes}/jobs.py` — são as
# quatro únicas filas reais do projeto (confirmado por busca em toda a
# auditoria F8.0; Assisted Outreach, Fase 7, é deliberadamente síncrono e
# não usa fila). `prototype_generation` adicionada na Fase 9 / Prompt 11.
# Se uma fila nova for criada, precisa ser adicionada aqui também, ou o
# worker nunca vai consumi-la.
DEFAULT_QUEUES = ["discovery", "audit", "briefing", "prototype_generation"]

logger = get_logger(__name__)


def main(queue_names: list[str] | None = None) -> None:
    settings = get_settings()
    configure_logging(log_level=settings.log_level, json_logs=settings.is_production)

    queues = queue_names or DEFAULT_QUEUES
    connection = get_redis_connection()

    logger.info("worker_starting", queues=queues, app_env=settings.app_env)

    worker = _WorkerClass(queues, connection=connection)
    worker.work(with_scheduler=False)


if __name__ == "__main__":
    main(sys.argv[1:] or None)
