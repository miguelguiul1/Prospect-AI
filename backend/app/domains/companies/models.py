"""Modelos do domínio `companies`.

Company é a identidade interna da empresa prospectada. Deliberadamente NÃO
possui nenhum campo de identificador de fonte externa (place_id, CNPJ, ID de
Instagram, etc.) — essa é a correção central da arquitetura v0.2 em relação
à v0.1. Toda ligação com uma fonte externa vive em `CompanySource`
(`app.domains.identity.models`), nunca aqui. Ver docs/data-model.md e
docs/architecture.md, seção "Identity Resolution".
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.domains.audit.models import AuditSnapshot
    from app.domains.evidence.models import Evidence
    from app.domains.identity.models import CompanySource


def _now() -> datetime:
    return datetime.now(timezone.utc)


class CompanyStatus(str, enum.Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class Region(Base):
    """Região geográfica normalizada usada em buscas e para agrupar empresas."""

    __tablename__ = "regions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    state: Mapped[str | None] = mapped_column(String(120), nullable=True)
    country: Mapped[str] = mapped_column(String(2), nullable=False, default="BR")

    companies: Mapped[list["Company"]] = relationship(back_populates="region")


class Category(Base):
    """Categoria/segmento de negócio normalizado.

    Existe desde a Fase 0 porque o Opportunity Score futuro (Fase 4) precisa
    de uma tabela de adequação por categoria, não de texto livre repetido.
    Nenhuma lógica de pontuação é implementada aqui.
    """

    __tablename__ = "categories"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)

    companies: Mapped[list["Company"]] = relationship(back_populates="category")


class Company(Base):
    """Identidade interna da empresa prospectada.

    Company ≠ identificador externo (arquitetura v0.2, seção 07/princípios).
    """

    __tablename__ = "companies"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    canonical_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    status: Mapped[CompanyStatus] = mapped_column(
        SAEnum(CompanyStatus, native_enum=False, length=20),
        nullable=False,
        default=CompanyStatus.ACTIVE,
    )

    region_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("regions.id"), nullable=True)
    category_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("categories.id"), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )

    region: Mapped["Region | None"] = relationship(back_populates="companies")
    category: Mapped["Category | None"] = relationship(back_populates="companies")

    sources: Mapped[list["CompanySource"]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )
    evidences: Mapped[list["Evidence"]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )
    audit_snapshots: Mapped[list["AuditSnapshot"]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )
