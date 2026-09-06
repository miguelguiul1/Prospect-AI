"""Endpoints de health check.

`/health` só confirma que o processo da aplicação está de pé — não toca
banco nem Redis, para ser seguro como probe de liveness. `/health/dependencies`
verifica conectividade real com Postgres e Redis, útil para diagnosticar o
ambiente local sem acoplar isso ao health check principal.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
def health(settings: Settings = Depends(get_settings)) -> dict:
    return {"status": "ok", "service": settings.app_name, "environment": settings.app_env}


@router.get("/health/dependencies")
def health_dependencies(db: Session = Depends(get_db)) -> dict:
    checks: dict[str, str] = {}

    try:
        db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:  # noqa: BLE001 - queremos reportar qualquer falha de dependência
        checks["database"] = f"error: {exc.__class__.__name__}"

    try:
        from app.jobs.queue import get_redis_connection

        get_redis_connection().ping()
        checks["redis"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["redis"] = f"error: {exc.__class__.__name__}"

    overall = "ok" if all(value == "ok" for value in checks.values()) else "degraded"
    return {"status": overall, "checks": checks}
