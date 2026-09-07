"""Autorização de `Prototype` (Prompt 10, antes da geração por IA da Fase 9).

`Prototype` não tem `owner_id` próprio (removido nesta fase — nunca foi
preenchido em nenhuma fase anterior, pré-datava a autenticação real da
Fase 7). O acesso é derivado exatamente como `Contact`
(`app.domains.crm.authorization`): "este usuário possui pelo menos uma
`Opportunity` para a `Company` deste `Prototype`" — reaproveita
`user_owns_any_opportunity_for_company` em vez de duplicar a lógica de
autorização em um segundo lugar que poderia divergir dela.

Sempre 404 (nunca 403) tanto para "não existe" quanto para "existe mas não
é acessível" — mesmo motivo já documentado em `crm.authorization`: não
vazar existência por enumeração de ID (Prompt 11 original, seção 4.3,
citado em `crm.authorization`).

Um `Prototype` com `company_id=None` (dado legado de antes desta fase, ver
`models.py`) nunca é acessível a ninguém por este caminho — não há empresa
contra a qual checar posse.
"""
from __future__ import annotations

import uuid

from fastapi import status
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.domains.auth.models import User
from app.domains.crm.authorization import user_owns_any_opportunity_for_company
from app.domains.prototypes.models import Prototype


def _not_found(prototype_id: uuid.UUID) -> AppError:
    return AppError(
        f"Prototype {prototype_id} não encontrado.",
        code="prototype_not_found",
        status_code=status.HTTP_404_NOT_FOUND,
    )


def get_accessible_prototype_or_404(db: Session, prototype_id: uuid.UUID, user: User) -> Prototype:
    prototype = db.get(Prototype, prototype_id)
    if prototype is None or prototype.company_id is None:
        raise _not_found(prototype_id)
    if not user_owns_any_opportunity_for_company(db, company_id=prototype.company_id, user_id=user.id):
        raise _not_found(prototype_id)
    return prototype


__all__ = ["get_accessible_prototype_or_404"]
