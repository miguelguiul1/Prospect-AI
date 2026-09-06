"""Orquestração do Prototype Builder: criar, listar, ler, atualizar e
excluir um `Prototype`. Nenhuma geração de código, nenhuma IA, nenhuma
execução de conteúdo do usuário — só CRUD validado.

Sobre "ownership" (seção 9/10 do Prompt 09): o Prospect AI não tem
autenticação em nenhuma fase até aqui (auditoria confirmou isso no início
da Fase 6 — zero JWT/OAuth/sessão em todo o backend). Não é possível
implementar isolamento por usuário sem inventar um sistema de autenticação
inteiro, que está fora do escopo desta fase (e de todas as anteriores).
Por isso `owner_id` existe na coluna mas nunca é lido de um campo enviado
pelo cliente nem usado para filtrar/autorizar nada nesta fase — documentado
como limitação conhecida, não como uma omissão silenciosa (ver
docs/prototype-builder.md).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

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

    def create(self, *, name: str, description: str | None = None) -> Prototype:
        prototype = Prototype(name=name, description=description, components=[], settings={})
        self._db.add(prototype)
        self._db.flush()
        return prototype

    def list(self, *, limit: int = 50, offset: int = 0) -> PrototypePage:
        total = self._db.query(Prototype).count()
        items = (
            self._db.query(Prototype)
            .order_by(Prototype.updated_at.desc())
            .limit(limit)
            .offset(offset)
            .all()
        )
        return PrototypePage(items=items, total=total, limit=limit, offset=offset)

    def get(self, prototype_id: uuid.UUID) -> Prototype | None:
        return self._db.get(Prototype, prototype_id)

    def update(
        self,
        prototype_id: uuid.UUID,
        *,
        name: str | None = None,
        description: str | None = None,
        components: list[dict] | None = None,
        settings: dict | None = None,
    ) -> Prototype:
        """Levanta `LookupError` se o protótipo não existe, ou `ValueError`
        se `components` não passar na validação estrutural (ver
        `schemas.validate_component_tree`) — nunca persiste uma árvore
        parcialmente válida."""
        prototype = self._db.get(Prototype, prototype_id)
        if prototype is None:
            raise LookupError(f"Prototype {prototype_id} não encontrado")

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

    def delete(self, prototype_id: uuid.UUID) -> bool:
        prototype = self._db.get(Prototype, prototype_id)
        if prototype is None:
            return False
        self._db.delete(prototype)
        self._db.flush()
        return True


__all__ = ["PrototypeService", "PrototypePage"]
