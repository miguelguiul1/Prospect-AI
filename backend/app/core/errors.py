"""Tratamento de erro consistente para toda a API.

Todo erro de aplicação vira uma resposta JSON no formato
`{"error": {"code": ..., "message": ...}}`. Erros não tratados são logados
com detalhe (para depuração interna) mas nunca expõem stack trace ou
mensagem de driver ao cliente.
"""
from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.core.logging import get_logger

logger = get_logger(__name__)


class AppError(Exception):
    """Erro de aplicação com código estável e status HTTP explícitos."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "app_error",
        status_code: int = status.HTTP_400_BAD_REQUEST,
    ) -> None:
        self.message = message
        self.code = code
        self.status_code = status_code
        super().__init__(message)


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    logger.warning("app_error", code=exc.code, message=exc.message, path=request.url.path)
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message}},
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error(
        "unhandled_exception",
        error_type=exc.__class__.__name__,
        error=str(exc),
        path=request.url.path,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": {"code": "internal_error", "message": "Erro interno inesperado."}},
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
