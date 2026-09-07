"""Hashing de senha e emissão/validação de token de acesso (Fase 7).

Estratégia definida pelo ADR-001 da auditoria F7.0: JWT próprio (`PyJWT`) +
hashing com `bcrypt` — sem provedor de identidade gerenciado externo, mesma
postura de zero-dependência-além-do-necessário já seguida pelo resto do
projeto. `bcrypt` já inclui salt por hash automaticamente; nunca reutilizamos
um salt manual.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt

from app.core.config import Settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_ALGORITHM_HEADER = "alg"


class TokenError(Exception):
    """Token ausente, malformado, expirado ou com assinatura inválida."""


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        # Hash corrompido/formato inesperado — nunca deixa vazar detalhe do
        # motivo, apenas trata como senha incorreta.
        return False


def _warn_if_insecure_secret(settings: Settings) -> None:
    if settings.is_production and settings.jwt_secret_key == "dev-insecure-secret-change-me":
        logger.error(
            "jwt_secret_key_insecure_in_production",
            hint="Defina JWT_SECRET_KEY no ambiente antes de operar em produção.",
        )


def create_access_token(user_id: uuid.UUID, *, settings: Settings) -> str:
    _warn_if_insecure_secret(settings)
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=settings.jwt_access_token_expire_minutes)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str, *, settings: Settings) -> uuid.UUID:
    """Retorna o `user_id` codificado no token, ou levanta `TokenError`.

    Nunca loga o token em si (poderia ser reutilizado por quem lesse o log)
    — apenas o tipo de falha.
    """
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("token expirado") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError("token inválido") from exc

    subject = payload.get("sub")
    if not subject:
        raise TokenError("token sem identificador de usuário")

    try:
        return uuid.UUID(subject)
    except ValueError as exc:
        raise TokenError("token com identificador de usuário malformado") from exc


__all__ = ["TokenError", "hash_password", "verify_password", "create_access_token", "decode_access_token"]
