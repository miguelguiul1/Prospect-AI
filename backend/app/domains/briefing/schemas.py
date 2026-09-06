"""Contrato de saída do Sales Brief.

Toda resposta do provider de IA passa por esta validação antes de ser
persistida — uma resposta que não valida (JSON malformado, campo faltando,
`talking_points` fora do intervalo permitido, texto vazio) nunca vira um
`SalesBrief.status=COMPLETED`; vira `FAILED` com o motivo registrado (ver
`app.domains.briefing.service`). Isto é o que a Fase 4 pede em "preferir
saída validada/estruturada; caso contrário, validar e rejeitar texto
inválido" — nunca aceitar cegamente o que o provider devolveu.
"""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

_MAX_FIELD_LENGTH = 2000


class SalesBriefContent(BaseModel):
    summary: str = Field(min_length=1, max_length=_MAX_FIELD_LENGTH)
    opportunity: str = Field(min_length=1, max_length=_MAX_FIELD_LENGTH)
    why_this_prospect: str = Field(min_length=1, max_length=_MAX_FIELD_LENGTH)
    digital_gaps: str = Field(min_length=1, max_length=_MAX_FIELD_LENGTH)
    suggested_angle: str = Field(min_length=1, max_length=_MAX_FIELD_LENGTH)
    talking_points: list[str] = Field(min_length=3, max_length=5)
    risks_and_caveats: str = Field(min_length=1, max_length=_MAX_FIELD_LENGTH)
    evidence_used: list[str] = Field(min_length=1, max_length=20)

    @field_validator("talking_points", "evidence_used")
    @classmethod
    def _no_blank_items(cls, items: list[str]) -> list[str]:
        cleaned = [item.strip() for item in items if item and item.strip()]
        if len(cleaned) != len(items):
            raise ValueError("itens de lista não podem ser vazios/em branco")
        return cleaned


__all__ = ["SalesBriefContent"]
