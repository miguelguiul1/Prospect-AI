"""Orquestração de autenticação: cadastro e login.

`register`/`authenticate` levantam `ValueError` para qualquer falha
esperada (e-mail já cadastrado, credenciais inválidas) — a rota HTTP
(`app.api.routes.auth`) traduz isso para 409/401, mesmo padrão de
`LookupError`/`ValueError` já usado em `PrototypeService`/`SalesBriefService`.

`authenticate` nunca revela SE foi o e-mail ou a senha que estava errada
(mesma mensagem genérica para os dois casos) — evita que um chamador use o
endpoint de login para descobrir quais e-mails têm conta.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.domains.auth.models import User
from app.domains.auth.security import hash_password, verify_password

_INVALID_CREDENTIALS_MESSAGE = "E-mail ou senha inválidos."


class AuthService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def register(self, *, email: str, name: str, password: str) -> User:
        existing = self._db.query(User).filter(User.email == email).first()
        if existing is not None:
            raise ValueError("Este e-mail já está cadastrado.")

        user = User(email=email, name=name, password_hash=hash_password(password))
        self._db.add(user)
        self._db.flush()
        return user

    def authenticate(self, *, email: str, password: str) -> User:
        user = self._db.query(User).filter(User.email == email).first()
        if user is None or not user.is_active:
            raise ValueError(_INVALID_CREDENTIALS_MESSAGE)
        if not verify_password(password, user.password_hash):
            raise ValueError(_INVALID_CREDENTIALS_MESSAGE)
        return user


__all__ = ["AuthService"]
