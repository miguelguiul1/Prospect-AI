"""Dependency central de identificação do usuário autenticado (Fase 7).

`get_current_user` é o ÚNICO lugar do backend que lê/decodifica o header
`Authorization` — toda rota protegida depende dela em vez de reimplementar
parsing de token (Prompt 11, seção 2.3: "não espalhe parsing de JWT/session
manualmente por todas as rotas"). Uma rota que não declara esta dependency
continua pública por padrão (ex.: `/api/health`, `/api/auth/login`) — isso é
uma escolha explícita de cada router, nunca um middleware global, porque
rotas de autenticação em si não podem exigir autenticação prévia.
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core import metrics
from app.core.config import Settings, get_settings
from app.core.logging import bind_request_context
from app.db.session import get_db
from app.domains.auth.models import User
from app.domains.auth.security import TokenError, decode_access_token

_WWW_AUTHENTICATE = {"WWW-Authenticate": "Bearer"}


def _unauthorized(detail: str, *, reason: str) -> HTTPException:
    # Métrica dedicada (Fase 8.6) — "authentication failures" é um dos
    # sinais explicitamente listados pela auditoria F8.0 como ausente.
    metrics.increment("auth_failures_total", {"reason": reason})
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail, headers=_WWW_AUTHENTICATE)


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> User:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise _unauthorized("Credenciais de autenticação não fornecidas.", reason="missing_token")

    token = auth_header.removeprefix("Bearer ").strip()
    if not token:
        raise _unauthorized("Credenciais de autenticação não fornecidas.", reason="missing_token")

    try:
        user_id = decode_access_token(token, settings=settings)
    except TokenError as exc:
        raise _unauthorized(str(exc), reason="invalid_token") from exc

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise _unauthorized("Usuário não encontrado ou inativo.", reason="user_not_found_or_inactive")

    # Associa user_id a todo log emitido pelo resto desta requisição (Fase
    # 8.6 — achado F8.0: nenhum log incluía identidade do usuário até aqui).
    # Nunca PII além do ID.
    bind_request_context(user_id=str(user.id))
    return user


__all__ = ["get_current_user"]
