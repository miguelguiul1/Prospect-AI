"""Agregador de routers da API. Novos domínios registram seus routers aqui
conforme forem implementados nas fases futuras."""
from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import discovery, health

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(discovery.router)
