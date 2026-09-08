"""Criação e leitura de `PrototypeVersion` (Fase 9 / Prompt 12).

`create_version` é o ÚNICO lugar que cria uma `PrototypeVersion` — tanto
`PrototypeGenerationService` (geração inicial e refinamento, Prompt 12)
quanto `PrototypeVersionService.restore` (abaixo) chamam esta mesma
função, nunca duplicam a lógica de "qual o próximo número" ou "atualizar
`Prototype.components`" em dois lugares que poderiam divergir com o
tempo. Ver a docstring de `PrototypeVersion`
(`app.domains.prototypes.models`) para a invariante completa e a
limitação documentada sobre edição manual via `PUT`.
"""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session, joinedload

from app.domains.prototypes.models import Prototype, PrototypeVersion


def create_version(
    db: Session,
    prototype: Prototype,
    *,
    components: list[dict],
    generation_run_id: uuid.UUID | None = None,
    restored_from_version_number: int | None = None,
) -> PrototypeVersion:
    """Cria a próxima `PrototypeVersion` (número = maior existente + 1,
    ou 1 se esta é a primeira) e atualiza `Prototype.components` para
    espelhá-la — sempre as duas coisas juntas, nunca uma sem a outra."""
    latest = (
        db.query(PrototypeVersion)
        .filter(PrototypeVersion.prototype_id == prototype.id)
        .order_by(PrototypeVersion.version_number.desc())
        .first()
    )
    next_number = (latest.version_number + 1) if latest is not None else 1

    version = PrototypeVersion(
        prototype_id=prototype.id,
        version_number=next_number,
        components=components,
        generation_run_id=generation_run_id,
        restored_from_version_number=restored_from_version_number,
    )
    db.add(version)
    db.flush()

    prototype.components = components
    db.flush()
    return version


class PrototypeVersionService:
    """Leitura e restauração de versões — nunca cria uma versão a partir
    de uma geração por IA (isso é `PrototypeGenerationService`); só lida
    com o histórico já existente."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def list_for_prototype(self, prototype_id: uuid.UUID) -> list[PrototypeVersion]:
        """Mais recente primeiro — ordem de exibição natural de um
        histórico ("o que aconteceu por último"). `joinedload` evita N+1
        ao montar a descrição de cada versão (que lê `generation_run.
        instruction`, ver `app.api.routes.prototypes._version_description`)."""
        return (
            self._db.query(PrototypeVersion)
            .options(joinedload(PrototypeVersion.generation_run))
            .filter(PrototypeVersion.prototype_id == prototype_id)
            .order_by(PrototypeVersion.version_number.desc())
            .all()
        )

    def get(self, prototype_id: uuid.UUID, version_id: uuid.UUID) -> PrototypeVersion | None:
        return (
            self._db.query(PrototypeVersion)
            .filter(PrototypeVersion.id == version_id, PrototypeVersion.prototype_id == prototype_id)
            .first()
        )

    def restore(self, prototype: Prototype, version: PrototypeVersion) -> PrototypeVersion:
        """Cria uma versão NOVA com os mesmos `components` da antiga —
        nunca um mecanismo especial de "voltar no tempo" que apaga ou
        reordena o histórico (seção 4 do Prompt 12: preferir isso a um
        mecanismo dedicado, por ser mais simples e mais consistente com o
        histórico linear já adotado)."""
        return create_version(
            self._db,
            prototype,
            components=version.components,
            restored_from_version_number=version.version_number,
        )


__all__ = ["create_version", "PrototypeVersionService"]
