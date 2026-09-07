"""Rate limiting best-effort baseado em Redis (Fase 7).

Mesmo espírito de `app.domains.discovery.cache`: o Redis já é uma
dependência declarada desde a Fase 0, e usá-lo para contagem de tentativas
não introduz nenhum componente novo de infraestrutura. Se o Redis estiver
indisponível, o limite é ignorado (nunca derruba a aplicação nem bloqueia um
usuário legítimo por causa de uma dependência opcional fora do ar) — a
falha é registrada como aviso, não silenciada.

Este NÃO é um rate limiter de propósito geral para toda a API (isso
permanece uma lacuna maior e separada, fora do escopo do F7 — ver a
auditoria F7.0, seção 18) — é uma contagem simples e explícita para os
pontos sensíveis identificados: login (força bruta) e geração de Outreach
por IA (custo).
"""
from __future__ import annotations

from app.core.logging import get_logger
from app.jobs.queue import get_redis_connection

logger = get_logger(__name__)


def check_and_increment(key: str, *, max_attempts: int, window_seconds: int) -> bool:
    """Incrementa o contador de `key` e retorna `True` se a requisição pode
    prosseguir (dentro do limite) ou `False` se deve ser rejeitada.

    Falha aberta (retorna `True`) se o Redis não puder ser alcançado — ver
    docstring do módulo.
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
            "rate_limit_check_unavailable_failing_open",
            key=key,
            error_type=exc.__class__.__name__,
        )
        return True


__all__ = ["check_and_increment"]
