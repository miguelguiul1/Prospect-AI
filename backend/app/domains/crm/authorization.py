"""Ponto único de autorização do domínio `crm` (Fase 7).

Toda rota que recebe um `{id}` de `Opportunity`/`Activity`/`Contact`/
`Outreach` passa por uma destas funções antes de fazer qualquer leitura ou
escrita — nunca confia em `owner_id` vindo do payload do cliente (Prompt 11,
seção 4.2: "o backend deve derivar o usuário da sessão/token"). Retorna
sempre 404 (nunca 403) tanto para "não existe" quanto para "existe mas não é
seu": distinguir os dois casos permitiria a um chamador confirmar por
enumeração que um determinado ID existe, mesmo sem acesso a ele — a mesma
defesa de "não vazar existência" já é uma prática padrão de mitigação de
IDOR (Prompt 11, seção 4.3).

Modelo de autorização desta primeira versão (ADR-003 da auditoria F7.0):
um único `owner_id` por `Opportunity`, sem papéis/times — qualquer usuário
autenticado só enxerga o que ele mesmo possui. Nenhum papel "admin" existe
ainda; se isso for necessário no futuro, é uma extensão aditiva (checar um
`User.role` antes de negar), não uma reescrita deste módulo.

`Contact` não pertence diretamente a um usuário (pertence a uma `Company`,
que continua sendo uma entidade compartilhada de inteligência, nunca
"dona" de ninguém) — o acesso a um `Contact` é derivado de "este usuário
possui pelo menos uma `Opportunity` (aberta ou não) para a empresa deste
contato", não de um `owner_id` próprio em `Contact`.
"""
from __future__ import annotations

import uuid

from fastapi import status
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.domains.auth.models import User
from app.domains.crm.models import Activity, Contact, Opportunity


def _not_found(entity: str, entity_id: uuid.UUID) -> AppError:
    return AppError(
        f"{entity} {entity_id} não encontrada.",
        code=f"{entity.lower()}_not_found",
        status_code=status.HTTP_404_NOT_FOUND,
    )


def get_owned_opportunity_or_404(db: Session, opportunity_id: uuid.UUID, user: User) -> Opportunity:
    opportunity = db.get(Opportunity, opportunity_id)
    if opportunity is None or opportunity.owner_id != user.id:
        raise _not_found("Opportunity", opportunity_id)
    return opportunity


def get_owned_activity_or_404(db: Session, activity_id: uuid.UUID, user: User) -> Activity:
    activity = db.get(Activity, activity_id)
    if activity is None:
        raise _not_found("Activity", activity_id)
    # Autorização é sempre derivada da Opportunity dona da atividade — nunca
    # existe um `owner_id` duplicado em Activity (evitaria uma segunda fonte
    # de verdade que poderia divergir da Opportunity).
    opportunity = db.get(Opportunity, activity.opportunity_id)
    if opportunity is None or opportunity.owner_id != user.id:
        raise _not_found("Activity", activity_id)
    return activity


def user_owns_any_opportunity_for_company(db: Session, *, company_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    return (
        db.query(Opportunity.id)
        .filter(Opportunity.company_id == company_id, Opportunity.owner_id == user_id)
        .first()
        is not None
    )


def get_accessible_contact_or_404(db: Session, contact_id: uuid.UUID, user: User) -> Contact:
    contact = db.get(Contact, contact_id)
    if contact is None or not user_owns_any_opportunity_for_company(
        db, company_id=contact.company_id, user_id=user.id
    ):
        raise _not_found("Contact", contact_id)
    return contact


__all__ = [
    "get_owned_opportunity_or_404",
    "get_owned_activity_or_404",
    "get_accessible_contact_or_404",
    "user_owns_any_opportunity_for_company",
]
