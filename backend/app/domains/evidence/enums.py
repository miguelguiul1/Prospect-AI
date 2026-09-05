"""Vocabulários fixos do Evidence Layer (arquitetura v0.2, seções 07/08/11).

`DataState` é o ponto mais importante deste arquivo: nenhuma checagem de
presença digital (site, Instagram, Facebook, WhatsApp, e-mail, Google
Business Profile, ...) pode colapsar "não verificado" ou "não confirmado"
em "não existe". Os seis estados abaixo existem exatamente para impedir essa
conversão silenciosa, exigida pelas seções 05 e 07 do prompt de arquitetura.
"""
from __future__ import annotations

import enum


class ConfidenceLevel(str, enum.Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class EvidenceMethod(str, enum.Enum):
    """Como um valor de Evidence foi obtido."""

    STRUCTURED_FIELD = "structured_field"
    HEURISTIC_MATCH = "heuristic_match"
    INFERENCE = "inference"
    MANUAL = "manual"


class DataState(str, enum.Enum):
    """Estado de uma checagem de presença digital ou de um dado coletado.

    CONFIRMED       — evidência confiável de que o fato é verdadeiro.
    NOT_DETECTED    — checagens completas não encontraram o fato.
    INCONCLUSIVE    — checagem incompleta ou ambígua; não decide nada.
    INACCESSIBLE    — há indício do fato, mas não foi possível confirmar
                       disponibilidade/acesso no momento da checagem.
    NOT_CHECKED     — a checagem ainda não foi executada (ex.: cota
                       esgotada, fonte não consultada nesta execução).
    STALE           — já foi confirmado no passado, mas ultrapassou o
                       limiar de validade e precisa ser reconfirmado.
    """

    CONFIRMED = "confirmed"
    NOT_DETECTED = "not_detected"
    INCONCLUSIVE = "inconclusive"
    INACCESSIBLE = "inaccessible"
    NOT_CHECKED = "not_checked"
    STALE = "stale"
