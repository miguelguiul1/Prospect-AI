"""Testes de `app.core.rate_limit` focados na limitação estrutural do
fallback local (Prompt 10, seção 2.4 — revalidação de um risco aberto
identificado no relatório final da Fase 8, nunca resolvido até aqui: "o
rate limiter local não é distribuído entre réplicas")."""
from __future__ import annotations

import threading

from app.core.rate_limit import (
    _local_fallback_attempts,
    _local_fallback_lock,
    check_and_increment,
    reset_local_fallback_state,
)


def test_local_fallback_state_is_a_plain_process_dict_not_distributed() -> None:
    """Prova estrutural, não só documentação em comentário: o estado do
    fallback local é um `dict` comum em memória do processo Python — nunca
    um cliente Redis, nunca nada que sobreviva a um restart ou seja visto
    por uma segunda réplica do backend. Se alguém no futuro trocar esta
    estrutura por algo distribuído, este teste passa a fazer menos sentido
    e deve levar a uma revisão da nota em `app/core/rate_limit.py` sobre o
    risco de múltiplas réplicas."""
    assert isinstance(_local_fallback_attempts, dict)
    assert isinstance(_local_fallback_lock, type(threading.Lock()))

    reset_local_fallback_state()
    check_and_increment(
        "ratelimit:structural-test:x", max_attempts=5, window_seconds=60, on_unavailable="local_fallback"
    )
    # O contador vive OBJETO Python local — nenhuma chamada de rede foi
    # feita para persistir isto em nenhum lugar compartilhado (Redis está
    # sempre indisponível nesta suíte, então qualquer persistência real
    # teria levantado um erro de conexão em vez de simplesmente funcionar).
    assert "ratelimit:structural-test:x" in _local_fallback_attempts
    reset_local_fallback_state()


def test_local_fallback_never_coordinates_between_two_independent_counters() -> None:
    """Simula duas "réplicas" ingenuamente — dois dicts Python separados
    nunca se enxergam — para tornar concreto, em um teste e não só em
    prosa, o que "não distribuído" realmente significa: o mesmo `key`
    logicamente idêntico, mas em dois processos, teria dois limites
    independentes, cada um permitindo até `max_attempts`, nunca um único
    limite global de `max_attempts` combinado."""
    reset_local_fallback_state()

    replica_a_allowed = [
        check_and_increment(
            "ratelimit:two-replicas:y", max_attempts=3, window_seconds=60, on_unavailable="local_fallback"
        )
        for _ in range(3)
    ]
    assert all(replica_a_allowed)

    # "Réplica B" seria um processo totalmente separado com seu próprio
    # dict vazio — simulado aqui resetando o estado antes de repetir a
    # mesma chave, para provar que ela recomeça do zero (nenhuma
    # coordenação real existiria entre processos de verdade).
    reset_local_fallback_state()
    replica_b_allowed = [
        check_and_increment(
            "ratelimit:two-replicas:y", max_attempts=3, window_seconds=60, on_unavailable="local_fallback"
        )
        for _ in range(3)
    ]
    assert all(replica_b_allowed), (
        "se isto falhar, o fallback deixou de ser puramente local — reveja a nota de "
        "múltiplas réplicas em app/core/rate_limit.py"
    )
    reset_local_fallback_state()
