"""Modelo do domínio `prototypes` (Fase 6 — Prototype Builder; `company_id`
adicionado no Prompt 10, antes da geração por IA da Fase 9).

`Prototype.components` guarda a árvore de componentes como uma lista PLANA
(cada item tem `parent_id` + `order`), não uma lista de listas aninhadas —
mais simples de atualizar (adicionar/mover/remover um nó não exige
reescrever a estrutura inteira) e trivial de reconstruir em árvore no
frontend a partir de `parent_id`. Cada item é validado contra
`app.domains.prototypes.schemas.PrototypeComponentInput` antes de ser
persistido (ver `service.py`) — nunca gravamos um componente com `type`
fora do catálogo permitido.

`company_id`: sem ele, era impossível responder "para qual empresa este
protótipo foi feito" — um bloqueador direto para a geração por IA (Fase 9),
que precisa saber de qual empresa puxar contexto (evidência, Sales Brief,
etc.). `nullable=True` no banco (decisão do Prompt 10, seção 1): a coluna
antiga `owner_id` (removida nesta migration — nunca foi preenchida em
nenhuma fase, era um placeholder de antes da Fase 7 existir de verdade)
não guardava nenhuma referência a empresa, então não há como inferir
`company_id` para protótipos criados antes desta migration sem inventar um
valor. Em vez de inventar uma empresa para esses registros órfãos (o que
seria pior — dado falso), a coluna aceita `NULL` para preservá-los sem
mentir sobre a origem deles; a partir desta fase, toda CRIAÇÃO nova exige
`company_id` obrigatoriamente (`PrototypeCreateRequest`, `service.create`)
— o `NULL` só existe para dado legado, nunca é um valor que o código atual
volta a produzir. Um protótipo com `company_id=None` fica permanentemente
inacessível pela API (`get_accessible_prototype_or_404` nunca resolve
`None` como pertencente a ninguém) até alguém corrigir manualmente no
banco — aceitável porque nenhum protótipo real de usuário existe hoje
nesta base (nenhum ambiente de produção jamais rodou esta fase).

Sem `owner_id` próprio — acesso é derivado exatamente como `Contact`
(`app.domains.crm.authorization.user_owns_any_opportunity_for_company`):
"este usuário tem uma Opportunity para a Company deste Prototype", nunca
uma coluna de dono duplicada que poderia divergir dessa fonte de verdade.
Ver `app/domains/prototypes/authorization.py`.
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Uuid
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Prototype(Base):
    __tablename__ = "prototypes"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)

    # NULL só para registros legados (ver docstring do módulo) — toda
    # criação nova via `PrototypeService.create` exige um valor real.
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("companies.id"), nullable=True, index=True
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)

    # Árvore de componentes, plana — ver docstring do módulo.
    components: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    # Configurações do protótipo como um todo (ex.: largura do canvas) —
    # nunca configuração de infraestrutura/segredos.
    settings: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )

    generation_runs: Mapped[list["GenerationRun"]] = relationship(
        back_populates="prototype", cascade="all, delete-orphan"
    )


class GenerationStatus(str, enum.Enum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class GenerationRun(Base):
    """Uma execução da geração por IA de um `Prototype` (Fase 9 /
    Prompt 11). Histórico preservado — nunca sobrescreve uma execução
    anterior, mesmo padrão de `SalesBrief`/`AuditSnapshot`.

    `status=FAILED` é um resultado válido e persistido, nunca mascarado —
    mesma regra de todo domínio que chama IA neste projeto desde a Fase 4.
    `error_code`/`error_message` (não um único campo `error`, ajuste
    deliberado sobre a sugestão original desta fase): mesmo padrão de
    `SalesBrief`, para que o motivo real de uma falha seja consultável
    programaticamente (por `error_code`), não só por um texto livre.

    Só uma execução `PENDING` por vez por `Prototype` (seção 5 do
    Prompt 11 — nunca duas gerações sobrescrevendo uma a outra) é
    aplicado em `PrototypeGenerationService`, não em uma constraint de
    banco: o estado "em andamento" é transitório por natureza (vira
    SUCCEEDED/FAILED assim que a chamada termina), então uma constraint
    de unicidade permanente seria desproporcional — a checagem síncrona no
    service já é suficiente e mais simples.
    """

    __tablename__ = "prototype_generation_runs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    prototype_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("prototypes.id"), nullable=False, index=True)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("companies.id"), nullable=False, index=True)

    status: Mapped[GenerationStatus] = mapped_column(
        SAEnum(GenerationStatus, native_enum=False, length=20), nullable=False
    )

    provider: Mapped[str | None] = mapped_column(String(40), nullable=True)
    model: Mapped[str | None] = mapped_column(String(80), nullable=True)
    prompt_version: Mapped[str] = mapped_column(String(10), nullable=False, default="v1")
    context_version: Mapped[str] = mapped_column(String(10), nullable=False, default="v1")

    # Só preenchidos quando o próprio provider os retorna — nunca
    # estimados (mesma regra de SalesBrief/Outreach).
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)

    error_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Avisos da heurística de grounding (seção 3 do Prompt 11) — nunca
    # bloqueiam a geração, só ficam visíveis para revisão humana depois.
    grounding_warnings: Mapped[list | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    prototype: Mapped["Prototype"] = relationship(back_populates="generation_runs")
    context_snapshot: Mapped["ContextSnapshot | None"] = relationship(
        back_populates="generation_run", uselist=False, cascade="all, delete-orphan"
    )


class ContextSnapshot(Base):
    """O `PrototypeContext` INTEIRO serializado (`PrototypeContext.to_dict()`),
    vinculado a um `GenerationRun` — imutável depois de criado (nenhum
    código deste projeto faz `UPDATE` numa linha existente). Isto é o que
    permite responder "por que a IA colocou isso aí" meses depois, mesmo
    que a Evidence da empresa já tenha mudado (seção 4 do Prompt 11)."""

    __tablename__ = "prototype_context_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    generation_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("prototype_generation_runs.id"), nullable=False, unique=True, index=True
    )

    context: Mapped[dict] = mapped_column(JSON, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)

    generation_run: Mapped["GenerationRun"] = relationship(back_populates="context_snapshot")
