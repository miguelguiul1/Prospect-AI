"""Modelos do domínio `discovery`.

`SearchRun` registra a intenção, os parâmetros normalizados e o resultado de
uma execução de descoberta (região + segmento). `ProviderUsageRecord` é um
log append-only de cada chamada real feita a um provider externo — existe
para responder "por que esta busca custou tanto" (arquitetura v0.2, seção
20) com granularidade por chamada, não só um total agregado.
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import Float, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class SearchRunStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIALLY_COMPLETED = "partially_completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SearchRun(Base):
    """Uma execução de descoberta (região + segmento) e seu resultado.

    Nunca é marcado `COMPLETED` se uma falha impediu a execução inteira —
    ver `app.domains.discovery.service`. `parameters` guarda a
    `DiscoveryQuery` já validada e normalizada, não a entrada bruta do
    operador.
    """

    __tablename__ = "search_runs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)

    region_query: Mapped[str] = mapped_column(String(255), nullable=False)
    segment_query: Mapped[str] = mapped_column(String(255), nullable=False)

    provider: Mapped[str] = mapped_column(String(60), nullable=False)
    parameters: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    status: Mapped[SearchRunStatus] = mapped_column(
        SAEnum(SearchRunStatus, native_enum=False, length=24),
        nullable=False,
        default=SearchRunStatus.PENDING,
    )

    raw_result_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    normalized_result_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    persisted_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    new_company_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pages_fetched: Mapped[int | None] = mapped_column(Integer, nullable=True)

    error_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)

    cost_estimate: Mapped[float | None] = mapped_column(Float, nullable=True)
    cost_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)

    requested_by: Mapped[str | None] = mapped_column(String(120), nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)

    usage_records: Mapped[list["ProviderUsageRecord"]] = relationship(
        back_populates="search_run", cascade="all, delete-orphan"
    )


class ProviderUsageRecord(Base):
    """Uma chamada real feita a um provider externo durante um `SearchRun`.

    Uma linha por requisição HTTP (uma página de resultados = uma linha) —
    não por resultado retornado. `estimated_cost` fica nulo quando nenhum
    preço foi configurado (ver `Settings.discovery_cost_per_request`);
    nenhum preço é assumido pelo código.
    """

    __tablename__ = "provider_usage_records"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    search_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("search_runs.id"), nullable=False, index=True
    )

    provider: Mapped[str] = mapped_column(String(60), nullable=False)
    operation: Mapped[str] = mapped_column(String(60), nullable=False)
    fields_requested: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    request_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    result_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    estimated_cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)

    search_run: Mapped["SearchRun"] = relationship(back_populates="usage_records")
