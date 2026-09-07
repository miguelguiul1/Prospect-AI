"""Ponto de entrada da aplicação Prospect AI.

Discovery, Identity Resolution, Digital Audit, Opportunity Scoring, Sales
Brief, CRM/Pipeline/Activities e Assisted Outreach estão todos ativos (ver
`app.api.router` para a lista completa de rotas registradas) — ver
README.md e docs/architecture.md para o estado real por fase.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import Settings, get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.core.middleware import RequestContextMiddleware, RequestSizeLimitMiddleware, SecurityHeadersMiddleware

logger = get_logger(__name__)

_INSECURE_DEFAULT_JWT_SECRET = "dev-insecure-secret-change-me"


def _validate_production_config(settings: Settings) -> None:
    """Fail-fast (Fase 8.3): antes desta fase, um JWT secret inseguro ou um
    CORS wildcard em produção só gerava um log de aviso — nada impedia a
    aplicação de subir insegura mesmo assim (achado R5 da auditoria F8.0).
    Chamado antes de qualquer rota existir; levanta `RuntimeError` (o
    processo nunca termina de subir) em vez de logar e seguir em frente.
    """
    if not settings.is_production:
        return

    if settings.jwt_secret_key == _INSECURE_DEFAULT_JWT_SECRET:
        raise RuntimeError(
            "JWT_SECRET_KEY não pode ser o valor padrão inseguro em produção "
            "(APP_ENV=production). Defina um valor real (ex.: `openssl rand -hex 32`) "
            "antes de subir a aplicação."
        )

    if "*" in settings.cors_allow_origins:
        raise RuntimeError(
            "CORS_ALLOW_ORIGINS não pode conter '*' em produção (APP_ENV=production). "
            "Liste explicitamente os domínios do frontend permitido."
        )


settings = get_settings()
configure_logging(log_level=settings.log_level, json_logs=settings.is_production)
_validate_production_config(settings)

app = FastAPI(title=settings.app_name, version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestContextMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestSizeLimitMiddleware, max_bytes=settings.max_request_body_bytes)

register_exception_handlers(app)
app.include_router(api_router)
