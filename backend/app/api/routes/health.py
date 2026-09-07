"""Endpoints de health check.

`/health` só confirma que o processo da aplicação está de pé — não toca
banco nem Redis, para ser seguro como probe de LIVENESS: nunca reporta
"morto" só porque uma dependência externa está lenta ou fora do ar.

`/health/dependencies` é a probe de READINESS (semântica formalizada na
Fase 8.6 — achado da auditoria F8.0, seção 12: antes desta fase, os dois
conceitos eram indistintos e Redis indisponível teria o mesmo peso que
PostgreSQL indisponível). Peso por dependência, não um "ok" tudo-ou-nada:

- **PostgreSQL indisponível → NOT READY** (HTTP 503): o sistema realmente
  não funciona sem banco — tirar a réplica de tráfego é o comportamento
  correto.
- **Redis indisponível → READY, `checks.redis` reporta "degraded"** (ainda
  HTTP 200): Redis é best-effort em todo o resto do sistema por desenho
  (fila com fallback síncrono desde F1, cache do Discovery, rate limiting
  com fail-closed/local-fallback desde F8.3) — tirar a réplica de tráfego
  por causa dele contradiria a própria filosofia de degradação graciosa já
  adotada em todo o projeto.
- **Anthropic**: reporta só se está CONFIGURADA (chave presente), nunca faz
  uma chamada de rede real — uma probe de readiness que gasta dinheiro/
  latência a cada execução (Kubernetes/orquestradores chamam isso a cada
  poucos segundos) seria um custo real sem necessidade. Nunca afeta
  readiness — o Opportunity Score e o resto do CRM não dependem dela.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session
from starlette.responses import JSONResponse

from app.core.config import Settings, get_settings
from app.db.session import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
def health(settings: Settings = Depends(get_settings)) -> dict:
    return {"status": "ok", "service": settings.app_name, "environment": settings.app_env}


@router.get("/health/dependencies")
def health_dependencies(
    db: Session = Depends(get_db), settings: Settings = Depends(get_settings)
) -> JSONResponse:
    checks: dict[str, str] = {}

    database_ready = True
    try:
        db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:  # noqa: BLE001 - queremos reportar qualquer falha de dependência
        checks["database"] = f"error: {exc.__class__.__name__}"
        database_ready = False

    try:
        from app.jobs.queue import get_redis_connection

        get_redis_connection().ping()
        checks["redis"] = "ok"
    except Exception as exc:  # noqa: BLE001
        # Nunca afeta `database_ready` — Redis é best-effort em todo o
        # resto do sistema (ver docstring do módulo).
        checks["redis"] = f"degraded: {exc.__class__.__name__}"

    checks["anthropic"] = "configured" if settings.anthropic_api_key else "not_configured"

    overall_status = "ok" if database_ready else "not_ready"
    status_code = 200 if database_ready else 503
    return JSONResponse(status_code=status_code, content={"status": overall_status, "checks": checks})
