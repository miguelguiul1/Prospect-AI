"""Vocabulário de decisão do Identity Resolution (Fase 2).

Reaproveita `ConfidenceLevel` do Evidence Layer (`app.domains.evidence.
enums`) para o grau de confiança de uma decisão — não duplicamos HIGH/
MEDIUM/LOW aqui. `MatchDecision` é um conceito novo e distinto de
`DataState`: `DataState` descreve o estado de uma checagem de presença
digital (Fase 3); `MatchDecision` descreve o resultado de comparar duas
identidades candidatas.
"""
from __future__ import annotations

import enum


class MatchDecision(str, enum.Enum):
    """Resultado de comparar um candidato contra uma `Company` existente.

    MATCH        — evidência forte o suficiente para tratar como a mesma
                    empresa (ver regra de segurança contra falsos
                    positivos em app.domains.identity.matching).
    NO_MATCH     — evidência concreta de que são empresas diferentes, ou
                    similaridade insuficiente para sequer suspeitar.
    INCONCLUSIVE — sinais parciais/contraditórios; nunca decide um merge
                    automático. Fica registrado para revisão humana
                    (`DedupCandidate.status = pending_review`).
    """

    MATCH = "match"
    NO_MATCH = "no_match"
    INCONCLUSIVE = "inconclusive"
