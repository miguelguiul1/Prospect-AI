"""Rate limiting baseado em Redis, com política diferenciada por
criticidade quando Redis está indisponível (Fase 8.3).

A Fase 7 tratava toda indisponibilidade de Redis da mesma forma
("fail-open" — permite tudo). A auditoria F8.0 confirmou ao vivo que isso
desativa simultaneamente a proteção contra força bruta de login e o
controle de custo de geração por IA, silenciosamente. Esta fase separa as
duas políticas, porque os riscos são de natureza diferente:

- **Login** (`on_unavailable="local_fallback"`): negar login por completo
  só porque uma dependência opcional (Redis) está fora do ar seria uma
  negação de serviço total — pior que o risco que se está mitigando. Em
  vez de fail-open puro, usa um contador local em memória do próprio
  processo como segunda linha de defesa.
- **Operações caras de IA** (`on_unavailable="fail_closed"` — Sales Brief,
  Assisted Outreach): o risco aqui é financeiro direto (custo da API da
  Anthropic), não disponibilidade do sistema. Bloquear a operação até
  Redis voltar é o comportamento correto — nenhuma chamada de IA sem
  controle de limite é aceitável.

Este NÃO é um rate limiter de propósito geral para toda a API — é uma
contagem explícita para os pontos sensíveis já identificados. Continua
usando o mesmo Redis já declarado como dependência desde a Fase 0.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict
from typing import Literal

from app.core.logging import get_logger
from app.jobs.queue import get_redis_connection

logger = get_logger(__name__)

OnUnavailablePolicy = Literal["fail_open", "fail_closed", "local_fallback"]

# Fallback local (por PROCESSO, nunca distribuído) usado somente quando a
# política é `local_fallback` E Redis está inacessível. Perdido a cada
# restart do processo; não coordena entre réplicas — nunca deve ser
# confundido com o rate limiter distribuído real. Documentado explicitamente
# em docs/production-readiness.md como uma degradação aceitável, não uma
# solução equivalente.
_local_fallback_lock = threading.Lock()
_local_fallback_attempts: dict[str, list[float]] = defaultdict(list)


def reset_local_fallback_state() -> None:
    """Limpa o contador local em memória — usado apenas pela suíte de
    testes (ver `tests/conftest.py`), para que o fallback de um teste nunca
    vaze para o próximo. Nunca chamado pelo código de aplicação em si."""
    with _local_fallback_lock:
        _local_fallback_attempts.clear()


def _local_fallback_check(key: str, *, max_attempts: int, window_seconds: int) -> bool:
    now = time.monotonic()
    with _local_fallback_lock:
        attempts = _local_fallback_attempts[key]
        attempts[:] = [t for t in attempts if now - t < window_seconds]
        if len(attempts) >= max_attempts:
            return False
        attempts.append(now)
        return True


def check_and_increment(
    key: str,
    *,
    max_attempts: int,
    window_seconds: int,
    on_unavailable: OnUnavailablePolicy = "fail_open",
) -> bool:
    """Incrementa o contador de `key` e retorna `True` se a requisição pode
    prosseguir (dentro do limite) ou `False` se deve ser rejeitada.

    Quando Redis está inacessível, o comportamento depende de
    `on_unavailable`:

    - `"fail_open"`: permite (comportamento legado — usar só para operações
      onde bloquear tudo seria pior que o risco do limite ausente).
    - `"fail_closed"`: bloqueia — usar para operações com custo financeiro
      direto (chamadas de IA).
    - `"local_fallback"`: usa um contador local não-distribuído como
      segunda linha de defesa — usar para login.
    """
    try:
        conn = get_redis_connection()
        pipe = conn.pipeline()
        pipe.incr(key)
        pipe.expire(key, window_seconds, nx=True)
        count, _ = pipe.execute()
        return int(count) <= max_attempts
    except Exception as exc:  # noqa: BLE001 - Redis indisponível é um modo operacional válido aqui
        logger.warning(
            "rate_limit_check_unavailable",
            key=key,
            policy=on_unavailable,
            error_type=exc.__class__.__name__,
        )
        if on_unavailable == "fail_closed":
            return False
        if on_unavailable == "local_fallback":
            return _local_fallback_check(key, max_attempts=max_attempts, window_seconds=window_seconds)
        return True


__all__ = ["check_and_increment", "OnUnavailablePolicy", "reset_local_fallback_state"]
