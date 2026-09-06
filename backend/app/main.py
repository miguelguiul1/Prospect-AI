"""Ponto de entrada da aplicação Prospect AI — Fase 0 (Foundation).

Nenhuma integração externa (Discovery, Digital Audit, Sales Brief) está
ativa nesta fase. Ver README.md e docs/architecture.md.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware

settings = get_settings()
configure_logging(log_level=settings.log_level, json_logs=settings.is_production)

app = FastAPI(title=settings.app_name, version="0.1.0-fase0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestContextMiddleware)

register_exception_handlers(app)
app.include_router(api_router)
