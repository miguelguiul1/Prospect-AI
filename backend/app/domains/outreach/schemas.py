"""Schemas do domínio `outreach` (Fase 7).

`OutreachContent` é o schema de VALIDAÇÃO da saída da IA — mesmo padrão de
`app.domains.briefing.schemas.SalesBriefContent`: se a resposta do provider
não validar contra isto, o rascunho nunca é salvo como pronto (Prompt 11,
seção 19.3).
"""
from __future__ import annotations

import uuid

from pydantic import BaseModel, Field, field_validator

from app.domains.outreach.enums import OutreachChannel


def _no_blank_items(items: list[str]) -> list[str]:
    cleaned = [item.strip() for item in items]
    if any(not item for item in cleaned):
        raise ValueError("itens da lista não podem ser vazios")
    return cleaned


class OutreachContent(BaseModel):
    subject: str = Field(min_length=1, max_length=300)
    message: str = Field(min_length=1, max_length=4000)
    rationale: str = Field(min_length=1, max_length=2000)
    evidence_ids: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("evidence_ids")
    @classmethod
    def _clean_evidence_ids(cls, value: list[str]) -> list[str]:
        return _no_blank_items(value) if value else value

    @field_validator("subject", "message", "rationale")
    @classmethod
    def _no_markup(cls, value: str) -> str:
        if "<" in value or ">" in value:
            raise ValueError("não é permitido HTML/markup na mensagem gerada")
        return value


class GenerateOutreachRequest(BaseModel):
    channel: OutreachChannel
    contact_id: uuid.UUID | None = None


class OutreachEditRequest(BaseModel):
    subject: str | None = Field(default=None, max_length=300)
    message: str | None = Field(default=None, max_length=4000)

    @field_validator("subject", "message")
    @classmethod
    def _no_markup(cls, value: str | None) -> str | None:
        if value and ("<" in value or ">" in value):
            raise ValueError("não é permitido HTML/markup neste campo")
        return value


class OutreachTransitionRequest(BaseModel):
    action: str = Field(min_length=1, max_length=20)  # "mark_ready" | "mark_sent" | "cancel"

    @field_validator("action")
    @classmethod
    def _valid_action(cls, value: str) -> str:
        if value not in {"mark_ready", "mark_sent", "cancel"}:
            raise ValueError("action deve ser 'mark_ready', 'mark_sent' ou 'cancel'")
        return value


__all__ = ["OutreachContent", "GenerateOutreachRequest", "OutreachEditRequest", "OutreachTransitionRequest"]
