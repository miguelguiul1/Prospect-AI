"""Enums do domínio `outreach` (Fase 7)."""
from __future__ import annotations

import enum


class OutreachChannel(str, enum.Enum):
    EMAIL = "email"
    WHATSAPP = "whatsapp"
    OTHER = "other"


class OutreachStatus(str, enum.Enum):
    """Nenhum status aqui significa "enviado pelo sistema" — o F7 implementa
    somente Assisted Outreach (Nível 1, auditoria F7.0): o próprio usuário
    envia manualmente fora do sistema e só então confirma `SENT_MANUALLY`.
    """

    DRAFT = "draft"
    READY = "ready"
    SENT_MANUALLY = "sent_manually"
    CANCELLED = "cancelled"
