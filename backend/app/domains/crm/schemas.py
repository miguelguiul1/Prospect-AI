"""Schemas de entrada do domínio `crm` (Fase 7).

Mesma disciplina de validação de `app.domains.prototypes.schemas`: tamanhos
máximos explícitos, texto sempre puro (nenhum campo aceita HTML — ver
`_no_markup`, mesma ideia de "primitivos curtos" já usada no Prototype
Builder). `ActivityCreateRequest` restringe os tipos que um usuário pode
criar diretamente: `STAGE_CHANGE`/`OWNERSHIP_CHANGED`/`SYSTEM`/`OUTREACH`
são sempre gerados internamente pelos próprios serviços (nunca por um
payload de cliente), para que a timeline continue sendo uma fonte confiável
do que o sistema realmente fez.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.domains.crm.enums import ActivityType, ContactValidationStatus, OpportunityPriority

_MANUALLY_CREATABLE_ACTIVITY_TYPES = {
    ActivityType.NOTE,
    ActivityType.TASK,
    ActivityType.CALL,
    ActivityType.MEETING,
    ActivityType.EMAIL,
    ActivityType.WHATSAPP,
}

_ALLOWED_CONTACT_SOURCES = {"manual", "imported", "form"}


def _no_markup(value: str) -> str:
    if "<" in value or ">" in value:
        raise ValueError("não é permitido HTML/markup neste campo")
    return value


class OpportunityCreateRequest(BaseModel):
    company_id: uuid.UUID
    priority: OpportunityPriority = OpportunityPriority.MEDIUM


class OpportunityStageChangeRequest(BaseModel):
    stage_key: str = Field(min_length=1, max_length=40)


class OpportunityOwnerChangeRequest(BaseModel):
    owner_id: uuid.UUID


class OpportunityCloseRequest(BaseModel):
    outcome: str = Field(min_length=1, max_length=10)  # "won" | "lost"
    reason: str | None = Field(default=None, max_length=500)

    @field_validator("outcome")
    @classmethod
    def _valid_outcome(cls, value: str) -> str:
        if value not in {"won", "lost"}:
            raise ValueError("outcome deve ser 'won' ou 'lost'")
        return value

    @field_validator("reason")
    @classmethod
    def _reason_no_markup(cls, value: str | None) -> str | None:
        return _no_markup(value) if value else value


class ContactCreateRequest(BaseModel):
    company_id: uuid.UUID
    name: str = Field(min_length=1, max_length=200)
    role: str | None = Field(default=None, max_length=120)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=50)
    source: str = Field(default="manual", max_length=30)

    @field_validator("name", "role")
    @classmethod
    def _text_no_markup(cls, value: str | None) -> str | None:
        return _no_markup(value) if value else value

    @field_validator("source")
    @classmethod
    def _valid_source(cls, value: str) -> str:
        if value not in _ALLOWED_CONTACT_SOURCES:
            raise ValueError(f"source deve ser um de {sorted(_ALLOWED_CONTACT_SOURCES)}")
        return value


class ContactUpdateRequest(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    role: str | None = Field(default=None, max_length=120)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=50)
    validation_status: ContactValidationStatus | None = None

    @field_validator("name", "role")
    @classmethod
    def _text_no_markup(cls, value: str | None) -> str | None:
        return _no_markup(value) if value else value


class ActivityCreateRequest(BaseModel):
    opportunity_id: uuid.UUID
    type: ActivityType
    title: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    due_at: datetime | None = None

    @field_validator("type")
    @classmethod
    def _manually_creatable(cls, value: ActivityType) -> ActivityType:
        if value not in _MANUALLY_CREATABLE_ACTIVITY_TYPES:
            raise ValueError(
                f"type '{value.value}' é gerado automaticamente pelo sistema e não pode ser criado diretamente"
            )
        return value

    @field_validator("title", "description")
    @classmethod
    def _text_no_markup(cls, value: str | None) -> str | None:
        return _no_markup(value) if value else value


class ActivityUpdateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    due_at: datetime | None = None
    completed: bool | None = None  # True -> marca DONE; False -> reabre (OPEN)

    @field_validator("title", "description")
    @classmethod
    def _text_no_markup(cls, value: str | None) -> str | None:
        return _no_markup(value) if value else value


__all__ = [
    "OpportunityCreateRequest",
    "OpportunityStageChangeRequest",
    "OpportunityOwnerChangeRequest",
    "OpportunityCloseRequest",
    "ContactCreateRequest",
    "ContactUpdateRequest",
    "ActivityCreateRequest",
    "ActivityUpdateRequest",
]
