"""Vocabulário próprio do domínio `audit`.

O estado do *site* (existe/não existe/inconclusivo/inacessível) reaproveita
`DataState`, já definido em `app.domains.evidence.enums` desde a Fase 0 —
os quatro valores que a Fase 3 pede (`confirmed`, `not_detected`,
`inconclusive`, `inaccessible`) já existem lá, mais dois que se encaixam
bem em casos que a Fase 3 precisa distinguir (`not_checked` para um
bloqueio de SSRF deliberado; `stale` reservado para quando uma fase futura
reauditar). Não duplicamos esse enum aqui.

`AuditStatus` é novo: describe o ciclo de vida da EXECUÇÃO da auditoria em
si (o processo rodou com sucesso ou falhou?) — um conceito diferente do
estado do site que ela investigou, no mesmo espírito de
`SearchRunStatus` vs. o resultado de uma busca.
"""
from __future__ import annotations

import enum


class AuditStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
