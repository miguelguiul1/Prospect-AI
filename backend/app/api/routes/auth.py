"""API HTTP de autenticação (Fase 7, rate limiting endurecido na Fase 8.3).

`POST /register` e `POST /login` são as únicas rotas públicas deste router
— tudo o mais no backend passa a depender de `get_current_user`. Ambas são
protegidas por rate limiting por e-mail (força bruta em login, abuso de
criação de conta em register), política `local_fallback`: se Redis estiver
fora do ar, um contador local por processo assume como segunda linha de
defesa — nunca equivalente a um limite distribuído real, mas nunca permite
tentativas totalmente ilimitadas como o fail-open puro da Fase 7 permitia
(ver `app.core.rate_limit`). `POST /logout` é um endpoint deliberadamente trivial:
como o token é um JWT stateless (sem sessão de servidor a invalidar), o
"logout" real acontece no cliente (descartar o token); o endpoint existe só
para o frontend ter um alvo explícito e simétrico, e para deixar essa
limitação documentada em vez de fingir uma invalidação que não existe.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.core.rate_limit import check_and_increment
from app.db.session import get_db
from app.domains.auth.dependencies import get_current_user
from app.domains.auth.models import User
from app.domains.auth.schemas import LoginRequest, RegisterRequest, TokenResponse, UserResponse
from app.domains.auth.security import create_access_token
from app.domains.auth.service import AuthService

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _to_user_response(user: User) -> UserResponse:
    return UserResponse(id=user.id, email=user.email, name=user.name, created_at=user.created_at)


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(
    payload: RegisterRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TokenResponse:
    allowed = check_and_increment(
        f"ratelimit:register:{payload.email}",
        max_attempts=settings.auth_register_rate_limit_max_attempts,
        window_seconds=settings.auth_register_rate_limit_window_seconds,
        on_unavailable="local_fallback",
    )
    if not allowed:
        raise AppError(
            "Muitas tentativas de cadastro. Tente novamente mais tarde.",
            code="rate_limited",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        )

    service = AuthService(db)
    try:
        user = service.register(email=payload.email, name=payload.name, password=payload.password)
    except ValueError as exc:
        raise AppError(str(exc), code="email_already_registered", status_code=status.HTTP_409_CONFLICT) from exc

    db.commit()
    db.refresh(user)
    token = create_access_token(user.id, settings=settings)
    return TokenResponse(access_token=token, user=_to_user_response(user))


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> TokenResponse:
    allowed = check_and_increment(
        f"ratelimit:login:{payload.email}",
        max_attempts=settings.auth_login_rate_limit_max_attempts,
        window_seconds=settings.auth_login_rate_limit_window_seconds,
        on_unavailable="local_fallback",
    )
    if not allowed:
        raise AppError(
            "Muitas tentativas de login. Tente novamente em alguns minutos.",
            code="rate_limited",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        )

    service = AuthService(db)
    try:
        user = service.authenticate(email=payload.email, password=payload.password)
    except ValueError as exc:
        raise AppError(str(exc), code="invalid_credentials", status_code=status.HTTP_401_UNAUTHORIZED) from exc

    token = create_access_token(user.id, settings=settings)
    return TokenResponse(access_token=token, user=_to_user_response(user))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout() -> None:
    """Sem estado de sessão no servidor (JWT stateless) — ver docstring do módulo."""
    return None


@router.get("/me", response_model=UserResponse)
def me(current_user: User = Depends(get_current_user)) -> UserResponse:
    return _to_user_response(current_user)
