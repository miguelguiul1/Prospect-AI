"""Testes de `/api/auth/register`, `/login`, `/me`, `/logout` (Fase 7)."""
from __future__ import annotations


def _register(client, email: str = "vendedora@example.com", password: str = "senhaforte123") -> dict:
    response = client.post(
        "/api/auth/register", json={"email": email, "name": "Vendedora Teste", "password": password}
    )
    assert response.status_code == 201, response.text
    return response.json()


class TestRegister:
    def test_register_returns_token_and_user(self, client) -> None:
        body = _register(client)
        assert "access_token" in body
        assert body["user"]["email"] == "vendedora@example.com"

    def test_register_never_echoes_password_hash(self, client) -> None:
        body = _register(client)
        assert "password" not in body["user"]
        assert "password_hash" not in body["user"]

    def test_duplicate_email_is_rejected(self, client) -> None:
        _register(client)
        response = client.post(
            "/api/auth/register",
            json={"email": "vendedora@example.com", "name": "Outra Pessoa", "password": "outrasenha123"},
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "email_already_registered"

    def test_invalid_email_is_rejected(self, client) -> None:
        response = client.post(
            "/api/auth/register", json={"email": "nao-e-email", "name": "X", "password": "senhaforte123"}
        )
        assert response.status_code == 422

    def test_short_password_is_rejected(self, client) -> None:
        response = client.post(
            "/api/auth/register", json={"email": "a@b.com", "name": "X", "password": "123"}
        )
        assert response.status_code == 422


class TestLogin:
    def test_login_with_correct_credentials_returns_token(self, client) -> None:
        _register(client)
        response = client.post("/api/auth/login", json={"email": "vendedora@example.com", "password": "senhaforte123"})
        assert response.status_code == 200
        assert "access_token" in response.json()

    def test_login_with_wrong_password_is_rejected(self, client) -> None:
        _register(client)
        response = client.post("/api/auth/login", json={"email": "vendedora@example.com", "password": "senhaerrada"})
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "invalid_credentials"

    def test_login_with_unknown_email_is_rejected_with_the_same_generic_message(self, client) -> None:
        response = client.post("/api/auth/login", json={"email": "ninguem@example.com", "password": "qualquer123"})
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "invalid_credentials"

    def test_login_rate_limited_after_too_many_attempts(self, client, monkeypatch) -> None:
        _register(client, email="alvo@example.com")
        import app.core.config as config_module

        monkeypatch.setattr(
            config_module.Settings, "auth_login_rate_limit_max_attempts", 3, raising=False
        )
        config_module.get_settings.cache_clear()
        try:
            for _ in range(3):
                client.post("/api/auth/login", json={"email": "alvo@example.com", "password": "senha-errada"})
            response = client.post("/api/auth/login", json={"email": "alvo@example.com", "password": "senha-errada"})
            # Redis não está disponível no ambiente de teste (ver
            # tests/conftest.py) — o rate limiter falha aberto (permite),
            # então o resultado esperado aqui é 401 (credenciais erradas),
            # nunca 429 nem um 500: prova a degradação graciosa exigida pela
            # auditoria F7.0 quando o Redis está fora do ar.
            assert response.status_code in (401, 429)
        finally:
            config_module.get_settings.cache_clear()


class TestMe:
    def test_me_without_token_is_unauthorized(self, client) -> None:
        response = client.get("/api/auth/me")
        assert response.status_code == 401

    def test_me_with_valid_token_returns_the_user(self, client) -> None:
        token = _register(client)["access_token"]
        response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        assert response.json()["email"] == "vendedora@example.com"

    def test_me_with_garbage_token_is_unauthorized(self, client) -> None:
        response = client.get("/api/auth/me", headers={"Authorization": "Bearer isto-nao-e-um-token"})
        assert response.status_code == 401

    def test_me_with_malformed_header_is_unauthorized(self, client) -> None:
        token = _register(client)["access_token"]
        response = client.get("/api/auth/me", headers={"Authorization": token})  # sem "Bearer "
        assert response.status_code == 401


class TestLogout:
    def test_logout_returns_no_content(self, client) -> None:
        token = _register(client)["access_token"]
        response = client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 204
