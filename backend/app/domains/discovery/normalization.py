"""Funções de normalização aplicadas a todo resultado antes da persistência.

Deliberadamente NÃO fazem deduplicação nem decidem identidade — apenas
limpam Unicode/espaços e padronizam formato (telefone, URL). Duas empresas
com nomes parecidos continuam sendo dois candidatos distintos nesta fase;
isso é trabalho da Fase 2 (Identity Resolution).
"""
from __future__ import annotations

import re
import unicodedata
from urllib.parse import urlsplit, urlunsplit

import phonenumbers

_WHITESPACE_RE = re.compile(r"\s+")


def normalize_whitespace(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    return _WHITESPACE_RE.sub(" ", normalized).strip()


def normalize_name(raw: str | None) -> str | None:
    if raw is None:
        return None
    cleaned = normalize_whitespace(raw)
    return cleaned or None


def normalize_address(raw: str | None) -> str | None:
    """Limpeza rasa (Unicode/espaços) apenas — não decompõe em
    logradouro/número/bairro. Endereços vêm do provider já formatados; uma
    decomposição estruturada, se necessária, é trabalho de uma fase futura."""
    if raw is None:
        return None
    cleaned = normalize_whitespace(raw)
    return cleaned or None


def normalize_category(raw: str | None) -> str | None:
    if raw is None:
        return None
    cleaned = normalize_whitespace(raw.replace("_", " ")).lower()
    return cleaned or None


def normalize_phone(raw: str | None, *, default_region: str = "BR") -> str | None:
    """Normaliza para E.164 (`+5511987654321`) quando possível.

    Retorna `None` se a fonte não informou telefone ou se o valor informado
    não é um número reconhecível — nunca inventa nem "corrige" um número
    que não conseguimos interpretar.
    """
    if raw is None:
        return None
    cleaned = normalize_whitespace(raw)
    if not cleaned:
        return None
    try:
        parsed = phonenumbers.parse(cleaned, default_region)
    except phonenumbers.NumberParseException:
        return None
    if not phonenumbers.is_possible_number(parsed):
        return None
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


def normalize_url(raw: str | None) -> str | None:
    """Garante esquema `https://` e remove espaços/barra final redundante.

    Retorna `None` se o valor não puder ser interpretado como URL — nunca
    força uma string arbitrária a parecer uma URL válida.
    """
    if raw is None:
        return None
    cleaned = raw.strip()
    if not cleaned:
        return None

    if "://" not in cleaned:
        cleaned = f"https://{cleaned}"

    parts = urlsplit(cleaned)
    if not parts.netloc:
        return None

    path = parts.path.rstrip("/") or ""
    normalized = urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, parts.query, ""))
    return normalized
