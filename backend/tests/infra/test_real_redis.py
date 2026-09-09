"""Validação contra Redis REAL (Fase 8) — nunca simulado.

Mesma filosofia de `test_real_postgres.py`: usa sua própria variável de
ambiente (`REAL_REDIS_URL`), independente do `REDIS_URL` que o resto da
suíte fixa deliberadamente para uma porta morta (`redis://localhost:6399/0`
— ver `tests/conftest.py`, comentário sobre `test_health.py`), exatamente
para poder testar o caminho de indisponibilidade sem tocar Redis real.

Se não houver Redis real acessível, a suíte inteira é pulada com motivo
explícito. Em CI, um serviço `redis:7-alpine` real é provisionado.
"""
from __future__ import annotations

import os
import time

import pytest
import redis as redis_lib

from app.core.rate_limit import check_and_increment

REAL_REDIS_URL = os.environ.get("REAL_REDIS_URL", "redis://localhost:6379/0")


def _redis_available() -> bool:
    try:
        conn = redis_lib.from_url(REAL_REDIS_URL, socket_connect_timeout=0.5, socket_timeout=0.5)
        return bool(conn.ping())
    except Exception:  # noqa: BLE001
        return False


pytestmark = pytest.mark.skipif(
    not _redis_available(),
    reason=(
        "Redis real indisponível (REAL_REDIS_URL não respondeu a PING). "
        "Esperado em ambiente de desenvolvimento local sem Docker — ver "
        "docs/production-readiness.md."
    ),
)


@pytest.fixture()
def redis_conn():
    conn = redis_lib.from_url(REAL_REDIS_URL, socket_connect_timeout=0.5, socket_timeout=0.5)
    yield conn
    # Limpa só as chaves criadas por este módulo de teste — nunca faz FLUSHDB
    # (poderia apagar dado real de outro uso do mesmo Redis).
    for key in conn.scan_iter(match="test:f8:*"):
        conn.delete(key)


class TestConnectivity:
    def test_ping(self, redis_conn) -> None:
        assert redis_conn.ping() is True


class TestRateLimiterAgainstRealRedis:
    """Prova, contra Redis de verdade, o que a suíte principal só consegue
    provar no caminho inverso (Redis ausente → fail-open, já testado
    extensivamente em F7/F7.5). Aqui: Redis PRESENTE → o limite realmente
    bloqueia — isto nunca foi executado com sucesso antes da Fase 8.

    `check_and_increment` (código de produção) obtém sua conexão Redis via
    `app.jobs.queue.get_redis_connection()`, que lê `Settings.redis_url` —
    ou seja, o `REDIS_URL` que `tests/conftest.py` fixa deliberadamente
    para uma porta morta (`redis://localhost:6399/0`) durante TODA a
    sessão de pytest, para exercitar o caminho de indisponibilidade em
    outros testes. Sem este fixture, toda esta classe bateria nessa porta
    morta em vez de `REAL_REDIS_URL` — o fixture aponta temporariamente o
    `REDIS_URL` do processo para o Redis real e limpa os dois
    `lru_cache` (`get_settings`, `get_redis_connection`) para que a
    mudança tenha efeito; `monkeypatch` desfaz o `os.environ` sozinho ao
    final de cada teste, então o `cache_clear()` final restaura o cliente
    apontado para a porta morta de novo, sem vazar para os testes
    seguintes."""

    @pytest.fixture(autouse=True)
    def _app_client_targets_real_redis(self, monkeypatch: pytest.MonkeyPatch):
        from app.core.config import get_settings
        from app.jobs.queue import get_redis_connection

        monkeypatch.setenv("REDIS_URL", REAL_REDIS_URL)
        get_settings.cache_clear()
        get_redis_connection.cache_clear()
        yield
        get_settings.cache_clear()
        get_redis_connection.cache_clear()

    def test_allows_requests_within_the_limit(self, redis_conn) -> None:
        key = "test:f8:rate:within-limit"
        results = [check_and_increment(key, max_attempts=5, window_seconds=60) for _ in range(5)]
        assert all(results), "todas as 5 primeiras tentativas deveriam ser permitidas"

    def test_blocks_after_the_limit_is_exceeded(self, redis_conn) -> None:
        key = "test:f8:rate:exceeds-limit"
        for _ in range(10):
            check_and_increment(key, max_attempts=10, window_seconds=60)
        blocked = check_and_increment(key, max_attempts=10, window_seconds=60)
        assert blocked is False, "a 11ª tentativa deveria ser bloqueada — prova real de fail-CLOSED com Redis presente"

    def test_window_expires_and_resets_the_counter(self, redis_conn) -> None:
        key = "test:f8:rate:window-expiry"
        for _ in range(3):
            check_and_increment(key, max_attempts=3, window_seconds=1)
        assert check_and_increment(key, max_attempts=3, window_seconds=1) is False

        time.sleep(1.2)

        assert check_and_increment(key, max_attempts=3, window_seconds=1) is True, (
            "após a janela expirar, uma nova tentativa deveria ser permitida de novo"
        )

    def test_different_keys_are_isolated(self, redis_conn) -> None:
        key_a = "test:f8:rate:isolation-a"
        key_b = "test:f8:rate:isolation-b"
        for _ in range(5):
            check_and_increment(key_a, max_attempts=5, window_seconds=60)
        assert check_and_increment(key_a, max_attempts=5, window_seconds=60) is False
        assert check_and_increment(key_b, max_attempts=5, window_seconds=60) is True, (
            "uma chave (ex.: outro usuário/e-mail) nunca deveria ser afetada pelo limite de outra"
        )
