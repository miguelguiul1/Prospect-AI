"""Enums do domínio `crm` (Fase 7).

`OpportunityStatus` (estado comercial) e `PipelineStage` (etapa do funil)
são deliberadamente conceitos separados (Prompt 11, seção 5.3) — misturá-los
obrigaria, por exemplo, uma etapa "Perdido" e um status `LOST` a significar
a mesma coisa de duas formas diferentes. `status` responde "esta
oportunidade está em jogo?"; `stage` responde "em que ponto do funil ela
está?".
"""
from __future__ import annotations

import enum


class OpportunityStatus(str, enum.Enum):
    OPEN = "open"
    WON = "won"
    LOST = "lost"
    ARCHIVED = "archived"


class OpportunityPriority(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ActivityType(str, enum.Enum):
    NOTE = "note"
    TASK = "task"
    CALL = "call"
    MEETING = "meeting"
    EMAIL = "email"
    WHATSAPP = "whatsapp"
    OUTREACH = "outreach"
    STAGE_CHANGE = "stage_change"
    OWNERSHIP_CHANGED = "ownership_changed"
    SYSTEM = "system"


class ActivityStatus(str, enum.Enum):
    """Só tem significado para `Activity.type == TASK` — nas demais, fica
    `None` (uma nota ou uma chamada registrada não têm um ciclo pendente/
    concluído)."""

    OPEN = "open"
    DONE = "done"


class ContactValidationStatus(str, enum.Enum):
    UNVERIFIED = "unverified"
    VERIFIED = "verified"
    INVALID = "invalid"
