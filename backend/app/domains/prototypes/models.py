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

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

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
