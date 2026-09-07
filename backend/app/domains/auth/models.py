"""Modelo do domínio `auth`.

`User` é a única fonte de identidade do Prospect AI a partir da Fase 7 —
nenhum outro domínio ganha seu próprio conceito de usuário. Deliberadamente
mínimo (ADR conceitual do F7.0: "não crie dados desnecessários"): apenas o
suficiente para autenticar e para servir de alvo de `owner_id`/`created_by`
em `Opportunity`/`Activity`/`Contact`/`Outreach`.

`password_hash` nunca é a senha em texto puro — ver `app.domains.auth.
security` (bcrypt). Nenhuma rota, log ou schema de resposta deste domínio
deve expor este campo.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )
