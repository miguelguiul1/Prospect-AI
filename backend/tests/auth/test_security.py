"""Testes unitários de hashing de senha e JWT (Fase 7) — sem banco/cliente."""
from __future__ import annotations

import time
import uuid

import jwt
import pytest

from app.core.config import Settings
from app.domains.auth.security import TokenError, create_access_token, decode_access_token, hash_password, verify_password


def _settings(**overrides) -> Settings:
    overrides.setdefault("jwt_secret_key", "test-secret")
    return Settings(**overrides)


class TestPasswordHashing:
    def test_hash_is_never_the_plain_password(self) -> None:
        hashed = hash_password("minhasenha123")
        assert hashed != "minhasenha123"

    def test_verify_accepts_correct_password(self) -> None:
        hashed = hash_password("minhasenha123")
        assert verify_password("minhasenha123", hashed) is True

    def test_verify_rejects_wrong_password(self) -> None:
        hashed = hash_password("minhasenha123")
        assert verify_password("outrasenha", hashed) is False

    def test_same_password_hashes_differently_each_time(self) -> None:
        # bcrypt gera um salt novo a cada chamada — nunca o mesmo hash duas vezes.
        assert hash_password("minhasenha123") != hash_password("minhasenha123")

    def test_verify_handles_corrupted_hash_without_raising(self) -> None:
        assert verify_password("qualquer", "hash-corrompido-invalido") is False


class TestAccessToken:
    def test_token_roundtrip_returns_the_same_user_id(self) -> None:
        settings = _settings()
        user_id = uuid.uuid4()
        token = create_access_token(user_id, settings=settings)
        assert decode_access_token(token, settings=settings) == user_id

    def test_token_signed_with_a_different_secret_is_rejected(self) -> None:
        settings_a = _settings(jwt_secret_key="secret-a")
        settings_b = _settings(jwt_secret_key="secret-b")
        token = create_access_token(uuid.uuid4(), settings=settings_a)
        with pytest.raises(TokenError):
            decode_access_token(token, settings=settings_b)

    def test_expired_token_is_rejected(self) -> None:
        settings = _settings(jwt_access_token_expire_minutes=0)
        user_id = uuid.uuid4()
        # Um token com exp no passado imediato — construído diretamente para
        # não depender de sleep real no teste.
        payload = {"sub": str(user_id), "iat": int(time.time()) - 10, "exp": int(time.time()) - 1}
        token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
        with pytest.raises(TokenError):
            decode_access_token(token, settings=settings)

    def test_malformed_token_is_rejected(self) -> None:
        settings = _settings()
        with pytest.raises(TokenError):
            decode_access_token("isto.nao.e-um-jwt-valido", settings=settings)

    def test_token_without_subject_is_rejected(self) -> None:
        settings = _settings()
        token = jwt.encode({"iat": 0, "exp": 9999999999}, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
        with pytest.raises(TokenError):
            decode_access_token(token, settings=settings)
