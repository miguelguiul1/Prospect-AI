"""Middleware HTTP compartilhado.

`RequestContextMiddleware` (Fase 0): correlação de requisições — gera (ou
propaga, se o chamador já enviar `X-Request-ID`) um identificador por
requisição, associa-o ao contexto de logging estruturado e registra
início/fim com duração.

`SecurityHeadersMiddleware`/`RequestSizeLimitMiddleware` (Fase 8.3):
hardening — achados R6/R7 da auditoria F8.0, confirmados por busca direta
("zero ocorrência de qualquer header de segurança ou limite de tamanho de
corpo em todo o backend").
"""
from __future__ import annotations

import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core import metrics
from app.core.logging import bind_request_context, clear_request_context, get_logger

logger = get_logger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"


def _route_template(request: Request) -> str:
    """Template da rota (ex.: `/api/crm/opportunities/{opportunity_id}`),
    nunca o path resolvido (que teria um UUID novo por requisição) — usar o
    path resolvido como label de métrica criaria cardinalidade sem limite,
    um dos erros mais comuns ao instrumentar uma API com IDs na URL."""
    route = request.scope.get("route")
    if route is not None and hasattr(route, "path"):
        return route.path
    return request.url.path  # sem rota casada (404) — path bruto é aceitável aqui


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER, str(uuid.uuid4()))
        bind_request_context(request_id=request_id)
        start = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            logger.error(
                "request_failed",
                method=request.method,
                path=request.url.path,
                duration_ms=duration_ms,
            )
            metrics.increment("http_requests_total", {"method": request.method, "path": _route_template(request), "status": "5xx"})
            raise
        else:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            logger.info(
                "request_completed",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=duration_ms,
            )
            status_class = f"{response.status_code // 100}xx"
            route_path = _route_template(request)
            metrics.increment("http_requests_total", {"method": request.method, "path": route_path, "status": status_class})
            metrics.observe("http_request_duration", duration_ms, {"method": request.method, "path": route_path})
            response.headers[REQUEST_ID_HEADER] = request_id
            return response
        finally:
            clear_request_context()


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Headers de segurança básicos em toda resposta (Fase 8.3).

    Esta é uma API JSON, não uma aplicação que renderiza HTML — por isso
    não inclui uma Content-Security-Policy própria (CSP protege contra
    injeção de script em página renderizada; o lugar correto para isso é o
    frontend Next.js, não aqui). `Strict-Transport-Security` é seguro
    enviar sempre, mesmo sobre HTTP em desenvolvimento — o navegador só o
    respeita quando a conexão já é HTTPS.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """Rejeita (413) qualquer requisição cujo `Content-Length` declarado
    exceda `Settings.max_request_body_bytes` (Fase 8.3) — antes de a
    aplicação começar a ler o corpo, não depois.

    Limitação aceita: só valida quando o cliente envia `Content-Length`
    (o caso de toda chamada real do frontend/testes deste projeto — nenhum
    endpoint usa upload em streaming/chunked). Uma requisição chunked sem
    `Content-Length` não é bloqueada por este middleware; os limites por
    campo do Pydantic (`max_length`) continuam sendo a segunda linha de
    defesa nesse caso.
    """

    def __init__(self, app, *, max_bytes: int) -> None:
        super().__init__(app)
        self._max_bytes = max_bytes

    async def dispatch(self, request: Request, call_next) -> Response:
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                declared_size = int(content_length)
            except ValueError:
                declared_size = None
            if declared_size is not None and declared_size > self._max_bytes:
                logger.warning(
                    "request_body_too_large",
                    path=request.url.path,
                    declared_size=declared_size,
                    max_bytes=self._max_bytes,
                )
                return JSONResponse(
                    status_code=413,
                    content={"error": {"code": "request_too_large", "message": "Corpo da requisição excede o limite permitido."}},
                )
        return await call_next(request)
