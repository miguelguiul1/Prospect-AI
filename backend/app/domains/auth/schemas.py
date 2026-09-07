"""Schemas de entrada/saída do domínio `auth`.

Mesma disciplina de validação já usada em `app.domains.prototypes.schemas`:
tamanhos máximos explícitos, nenhum campo aceito sem validação. `EmailStr`
do Pydantic exigiria a dependência opcional `email-validator`, que o projeto
não tem — em vez de adicioná-la só por isso, usamos um regex simples e
suficiente para o caso de uso (validação de posse real de e-mail acontece,
na prática, por login bem-sucedido, não por checagem de formato).
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=8, max_length=200)

    @field_validator("email")
    @classmethod
    def _valid_email(cls, value: str) -> str:
        value = value.strip().lower()
        if not _EMAIL_RE.match(value):
            raise ValueError("email inválido")
        return value

    @field_validator("name")
    @classmethod
    def _non_blank_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name não pode ser vazio")
        return value


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=200)

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    name: str
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


__all__ = ["RegisterRequest", "LoginRequest", "UserResponse", "TokenResponse"]
