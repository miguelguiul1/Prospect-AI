"""Busca HTTP segura de uma URL candidata a website.

Nunca segue redirecionamento automaticamente (`follow_redirects=False`) —
cada hop é revalidado contra SSRF antes de ser seguido (arquitetura Fase 3,
seção 5). Nunca baixa mais do que `Settings.audit_http_max_response_bytes`
(leitura em streaming, interrompida ao atingir o limite). Nunca tenta
contornar bloqueio/erro do site — qualquer resposta não-redirect (incluindo
4xx/5xx) é devolvida como resultado, não como exceção; só falhas de rede,
timeout ou SSRF viram `FetchError`/`UnsafeURLError`.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from urllib.parse import urljoin

import httpx

from app.core.config import Settings
from app.core.logging import get_logger
from app.domains.audit.ssrf import ResolverFn, default_resolve, validate_url_is_safe

logger = get_logger(__name__)

_REDIRECT_STATUS_CODES = frozenset({301, 302, 303, 307, 308})


class FetchError(Exception):
    def __init__(self, message: str, *, reason: str) -> None:
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True)
class FetchResult:
    requested_url: str
    final_url: str
    status_code: int
    headers: dict[str, str]
    content_type: str | None
    body: bytes
    truncated: bool
    elapsed_ms: float
    redirect_chain: list[str] = field(default_factory=list)

    @property
    def is_https(self) -> bool:
        return self.final_url.startswith("https://")


def fetch_safely(
    url: str,
    *,
    settings: Settings,
    client: httpx.Client | None = None,
    resolver: ResolverFn = default_resolve,
) -> FetchResult:
    owns_client = client is None
    http_client = client or httpx.Client(
        follow_redirects=False,
        timeout=httpx.Timeout(
            connect=settings.audit_http_connect_timeout_seconds,
            read=settings.audit_http_read_timeout_seconds,
            write=settings.audit_http_read_timeout_seconds,
            pool=settings.audit_http_connect_timeout_seconds,
        ),
        headers={"User-Agent": settings.audit_http_user_agent},
    )

    try:
        current_url = url
        redirect_chain: list[str] = []
        start = time.perf_counter()

        for hop in range(settings.audit_http_max_redirects + 1):
            validate_url_is_safe(current_url, resolver=resolver)  # levanta UnsafeURLError se inseguro

            response = _send_with_retry(http_client, current_url, settings)

            if response.status_code in _REDIRECT_STATUS_CODES:
                location = response.headers.get("location")
                response.close()
                if not location:
                    raise FetchError("redirecionamento sem header Location", reason="redirect_without_location")
                next_url = urljoin(current_url, location)
                if hop >= settings.audit_http_max_redirects:
                    raise FetchError(
                        f"número máximo de redirecionamentos excedido ({settings.audit_http_max_redirects})",
                        reason="too_many_redirects",
                    )
                redirect_chain.append(next_url)
                current_url = next_url
                continue

            body, truncated = _read_capped(response, settings.audit_http_max_response_bytes)
            headers = dict(response.headers)
            status_code = response.status_code
            response.close()
            elapsed_ms = (time.perf_counter() - start) * 1000

            return FetchResult(
                requested_url=url,
                final_url=current_url,
                status_code=status_code,
                headers=headers,
                content_type=headers.get("content-type"),
                body=body,
                truncated=truncated,
                elapsed_ms=elapsed_ms,
                redirect_chain=redirect_chain,
            )

        raise FetchError(
            f"número máximo de redirecionamentos excedido ({settings.audit_http_max_redirects})",
            reason="too_many_redirects",
        )
    except httpx.TimeoutException as exc:
        raise FetchError(f"timeout ao buscar {current_url}: {exc.__class__.__name__}", reason="timeout") from exc
    except httpx.TransportError as exc:
        raise FetchError(
            f"falha de conexão ao buscar {current_url}: {exc.__class__.__name__}", reason="connection_failed"
        ) from exc
    finally:
        if owns_client:
            http_client.close()


def _send_with_retry(client: httpx.Client, url: str, settings: Settings) -> httpx.Response:
    """Retry limitado só para erros claramente transitórios (timeout,
    conexão recusada) — nunca para 4xx/5xx, que são respostas válidas do
    servidor e não erros de transporte. Nunca retry infinito."""
    attempt = 0
    while True:
        try:
            request = client.build_request("GET", url)
            return client.send(request, stream=True)
        except (httpx.TimeoutException, httpx.ConnectError) as exc:
            if attempt >= settings.audit_http_max_retries:
                raise
            delay = min(
                settings.audit_http_backoff_base_seconds * (2**attempt),
                settings.audit_http_backoff_max_seconds,
            )
            logger.warning(
                "audit_http_retry",
                url=url,
                attempt=attempt + 1,
                delay_seconds=delay,
                error_type=exc.__class__.__name__,
            )
            time.sleep(delay)
            attempt += 1


def _read_capped(response: httpx.Response, max_bytes: int) -> tuple[bytes, bool]:
    chunks: list[bytes] = []
    total = 0
    truncated = False

    for chunk in response.iter_bytes():
        total += len(chunk)
        if total > max_bytes:
            remaining = max_bytes - (total - len(chunk))
            if remaining > 0:
                chunks.append(chunk[:remaining])
            truncated = True
            break
        chunks.append(chunk)

    return b"".join(chunks), truncated
