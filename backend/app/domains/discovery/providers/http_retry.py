"""Loop de retry genérico para chamadas de provider.

Só repete exceções marcadas `retryable=True` (timeout, conexão, 429, 5xx —
ver `errors.py`). Erros permanentes (parâmetro inválido, credencial
rejeitada) propagam na primeira tentativa. `max_retries` limita o número
de tentativas extras — nunca há retry infinito.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from app.core.logging import get_logger
from app.domains.discovery.providers.errors import DiscoveryProviderError

logger = get_logger(__name__)

T = TypeVar("T")


def call_with_retry(
    func: Callable[[], T],
    *,
    max_retries: int,
    backoff_base_seconds: float,
    backoff_max_seconds: float,
    sleep_fn: Callable[[float], None],
) -> T:
    attempt = 0
    while True:
        try:
            return func()
        except DiscoveryProviderError as exc:
            if not exc.retryable or attempt >= max_retries:
                raise
            delay = min(backoff_base_seconds * (2**attempt), backoff_max_seconds)
            logger.warning(
                "discovery_provider_retry",
                attempt=attempt + 1,
                max_retries=max_retries,
                delay_seconds=delay,
                error_type=exc.__class__.__name__,
            )
            sleep_fn(delay)
            attempt += 1
