"""Orquestração do Prototype Builder: criar, listar, atualizar e excluir
um `Prototype`. Nenhuma geração de código, nenhuma IA, nenhuma execução de
conteúdo do usuário — só CRUD validado.

Sobre ownership (Prompt 10): `create` exige `company_id` e verifica que o
usuário chamador tem uma `Opportunity` para essa empresa antes de permitir
a criação — o mesmo critério usado depois para ler/editar/excluir (ver
`app.domains.prototypes.authorization.get_accessible_prototype_or_404`).
Sem essa checagem na criação, um usuário poderia criar um `Prototype`
vinculado a uma empresa que nunca prospectou e nunca mais conseguir
acessá-lo (já que a leitura exige a mesma posse) — inconsistente, não uma
falha de segurança em si, mas confuso o suficiente para justificar a
mesma regra nos dois lugares.

`get`/`update`/`delete` recebem o objeto `Prototype` já carregado e
autorizado pela rota (mesmo padrão de `OpportunityService.change_stage`
em `app.domains.crm.service`) — não recebem mais um `prototype_id` cru,
para nunca existir um caminho de escrita que pule a checagem de
autorização por engano.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.domains.companies.models import Company
from app.domains.crm.authorization import user_owns_any_opportunity_for_company
from app.domains.prototypes.models import Prototype
from app.domains.prototypes.schemas import validate_component_tree


@dataclass(frozen=True)
class PrototypePage:
    items: list[Prototype]
    total: int
    limit: int
    offset: int


class PrototypeService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def create(
        self, *, name: str, description: str | None, company_id: uuid.UUID, user_id: uuid.UUID
    ) -> Prototype:
        """Levanta `LookupError` se a empresa não existe, ou `PermissionError`
        se o usuário não tem nenhuma Opportunity para ela — ambos os casos
        viram 404 na rota (nunca 403), mesmo padrão do resto do CRM."""
        company = self._db.get(Company, company_id)
        if company is None:
            raise LookupError(f"Company {company_id} não encontrada")
        if not user_owns_any_opportunity_for_company(self._db, company_id=company_id, user_id=user_id):
            raise PermissionError(f"Usuário não tem acesso à empresa {company_id}")

        prototype = Prototype(
            name=name, description=description, company_id=company_id, components=[], settings={}
        )
        self._db.add(prototype)
        self._db.flush()
        return prototype

    def list_for_user(self, *, user_id: uuid.UUID, limit: int = 50, offset: int = 0) -> PrototypePage:
        """Só protótipos de empresas para as quais o usuário tem alguma
        Opportunity — nunca a lista inteira de todos os usuários."""
        from sqlalchemy import select

        from app.domains.crm.models import Opportunity

        accessible_company_ids = (
            select(Opportunity.company_id).where(Opportunity.owner_id == user_id).scalar_subquery()
        )
        query = self._db.query(Prototype).filter(Prototype.company_id.in_(accessible_company_ids))

        total = query.count()
        items = query.order_by(Prototype.updated_at.desc()).limit(limit).offset(offset).all()
        return PrototypePage(items=items, total=total, limit=limit, offset=offset)

    def update(
        self,
        prototype: Prototype,
        *,
        name: str | None = None,
        description: str | None = None,
        components: list[dict] | None = None,
        settings: dict | None = None,
    ) -> Prototype:
        """Levanta `ValueError` se `components` não passar na validação
        estrutural (ver `schemas.validate_component_tree`) — nunca persiste
        uma árvore parcialmente válida."""
        if name is not None:
            prototype.name = name
        if description is not None:
            prototype.description = description
        if components is not None:
            validated = validate_component_tree(components)
            prototype.components = [node.model_dump() for node in validated]
        if settings is not None:
            prototype.settings = settings

        self._db.flush()
        return prototype

    def delete(self, prototype: Prototype) -> None:
        self._db.delete(prototype)
        self._db.flush()


__all__ = ["PrototypeService", "PrototypePage"]
