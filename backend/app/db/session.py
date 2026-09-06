"""Engine e fábrica de sessões do SQLAlchemy.

Sessões são síncronas de propósito: a carga da Fase 0 é apenas HTTP simples
e a fila de jobs futura (RQ) também é síncrona por worker — introduzir
SQLAlchemy assíncrono agora adicionaria complexidade sem um requisito real
que a justifique.
"""
from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

# Garante que TODOS os modelos estejam registrados no mapper registry do
# SQLAlchemy antes que qualquer sessão seja usada — sem isso, um
# relationship() declarado com o nome da classe em string (ex.:
# `Mapped[list["AuditSnapshot"]]` em Company) só resolve corretamente se
# aquele módulo já tiver sido importado por algum outro caminho. Isso
# passava despercebido nos testes porque `migrations/env.py` importa
# `models_registry` antes de qualquer teste rodar — mas um processo real
# (`uvicorn app.main:app`) sem essa importação explícita falhava ao criar
# a primeira instância de `Company`. Ver docs/development.md.
from app.db import models_registry  # noqa: F401

_settings = get_settings()

engine = create_engine(_settings.database_url, pool_pre_ping=True, future=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
