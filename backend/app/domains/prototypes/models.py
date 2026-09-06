"""Modelo do domínio `prototypes` (Fase 6 — Prototype Builder).

`Prototype.components` guarda a árvore de componentes como uma lista PLANA
(cada item tem `parent_id` + `order`), não uma lista de listas aninhadas —
mais simples de atualizar (adicionar/mover/remover um nó não exige
reescrever a estrutura inteira) e trivial de reconstruir em árvore no
frontend a partir de `parent_id`. Cada item é validado contra
`app.domains.prototypes.schemas.PrototypeComponentInput` antes de ser
persistido (ver `service.py`) — nunca gravamos um componente com `type`
fora do catálogo permitido.

`owner_id` existe, mas nunca é preenchido nem validado nesta fase: o
Prospect AI não tem autenticação em nenhuma fase até aqui (confirmado por
auditoria — nenhum JWT/OAuth/sessão em todo o backend). Reservado para
quando uma fase futura de autenticação existir, no mesmo espírito de
`SearchRun.requested_by` (Fase 1) — nunca um valor inventado a partir de
um `userId` enviado pelo frontend.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Prototype(Base):
    __tablename__ = "prototypes"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)

    # Reservado para autenticação futura — nunca lido do frontend nesta fase
    # (ver docstring do módulo). `String`, não FK: não há tabela de usuários.
    owner_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)

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
