"""Endpoint de métricas (Fase 8.6) — texto de exposição do Prometheus.

Sem autenticação, no mesmo espírito de `/health`: um endpoint de
observabilidade não deveria depender de login para um coletor de métricas
alcançá-lo. Em produção, isto deveria ficar atrás de uma rede interna/
reverse proxy, não exposto publicamente sem restrição — não implementado
aqui (decisão de infraestrutura de deploy, fora do escopo do código).
"""
from __future__ import annotations

from fastapi import APIRouter
from starlette.responses import PlainTextResponse

from app.core.metrics import render_prometheus_text

router = APIRouter(tags=["metrics"])


@router.get("/metrics", response_class=PlainTextResponse)
def get_metrics() -> str:
    return render_prometheus_text()
