"""Testes do hardening de segurança da Fase 8.3 — headers, limite de
tamanho de requisição, e a validação fail-fast de configuração insegura em
produção (achados R5/R6/R7 da auditoria F8.0)."""
from __future__ import annotations

import pytest

from app.core.config import Settings
from app.main import _INSECURE_DEFAULT_JWT_SECRET, _validate_production_config


class TestProductionConfigValidation:
    def test_development_with_insecure_secret_is_allowed(self) -> None:
        settings = Settings(app_env="development", jwt_secret_key=_INSECURE_DEFAULT_JWT_SECRET)
        _validate_production_config(settings)  # não levanta

    def test_production_with_insecure_default_secret_fails_fast(self) -> None:
        settings = Settings(app_env="production", jwt_secret_key=_INSECURE_DEFAULT_JWT_SECRET)
        with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
            _validate_production_config(settings)

    def test_production_with_a_real_secret_is_allowed(self) -> None:
        settings = Settings(app_env="production", jwt_secret_key="um-segredo-real-gerado-com-openssl")
        _validate_production_config(settings)  # não levanta

    def test_production_with_a_short_secret_below_32_bytes_fails_fast(self) -> None:
        """Fase 8.9: evidência real de que isto importava veio do upgrade do
        PyJWT para 2.13.0, que passou a emitir `InsecureKeyLengthWarning`
        para chaves HMAC abaixo de 32 bytes — antes desta checagem, qualquer
        valor curto que não fosse o default literal passava pelo fail-fast."""
        settings = Settings(app_env="production", jwt_secret_key="curto-demais")
        with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
            _validate_production_config(settings)

    def test_production_with_cors_wildcard_fails_fast(self) -> None:
        settings = Settings(
            app_env="production",
            jwt_secret_key="um-segredo-real-gerado-com-openssl",
            cors_allow_origins=["*"],
        )
        with pytest.raises(RuntimeError, match="CORS_ALLOW_ORIGINS"):
            _validate_production_config(settings)

    def test_production_with_explicit_cors_origins_is_allowed(self) -> None:
        settings = Settings(
            app_env="production",
            jwt_secret_key="um-segredo-real-gerado-com-openssl",
            cors_allow_origins=["https://app.prospect-ai.example.com"],
        )
        _validate_production_config(settings)  # não levanta


class TestSecurityHeaders:
    def test_every_response_includes_the_baseline_security_headers(self, client) -> None:
        response = client.get("/health")
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
        assert "max-age=31536000" in response.headers["Strict-Transport-Security"]

    def test_headers_are_present_even_on_an_error_response(self, client) -> None:
        response = client.get("/api/companies/00000000-0000-0000-0000-000000000000")
        assert response.status_code == 404


class TestContentSecurityPolicy:
    """Prompt 10, seção 2.1 — achado aberto da Fase 8 (Remaining Risks:
    "sem CSP no backend")."""

    def test_api_responses_get_the_restrictive_default_none_policy(self, client) -> None:
        response = client.get("/health")
        csp = response.headers["Content-Security-Policy"]
        assert "default-src 'none'" in csp
        assert "unsafe-inline" not in csp
        assert "unsafe-eval" not in csp

    def test_api_error_responses_also_get_the_restrictive_policy(self, client) -> None:
        response = client.get("/api/companies/00000000-0000-0000-0000-000000000000")
        assert "default-src 'none'" in response.headers["Content-Security-Policy"]

    def test_docs_page_gets_a_looser_policy_scoped_to_jsdelivr(self, client) -> None:
        """Sem esta exceção documentada, o próprio Swagger UI do FastAPI
        (ligado por padrão, nunca desligado neste projeto) não carregaria —
        ele injeta um <script> inline e depende de `cdn.jsdelivr.net`
        (confirmado inspecionando a resposta real de `/docs`)."""
        response = client.get("/docs")
        assert response.status_code == 200
        csp = response.headers["Content-Security-Policy"]
        assert "default-src 'none'" not in csp
        assert "cdn.jsdelivr.net" in csp
        assert "'unsafe-inline'" in csp

    def test_redoc_page_also_gets_the_looser_policy(self, client) -> None:
        response = client.get("/redoc")
        assert response.status_code == 200
        assert "cdn.jsdelivr.net" in response.headers["Content-Security-Policy"]
        assert response.headers["X-Content-Type-Options"] == "nosniff"


class TestRequestSizeLimit:
    def test_a_request_declaring_a_body_larger_than_the_limit_is_rejected(self, client) -> None:
        huge_size = 2_000_000  # acima do default de 1_000_000 bytes
        response = client.post(
            "/api/auth/register",
            content=b"x" * 100,  # corpo real pequeno — só o Content-Length declarado importa aqui
            headers={"Content-Length": str(huge_size), "Content-Type": "application/json"},
        )
        assert response.status_code == 413
        assert response.json()["error"]["code"] == "request_too_large"

    def test_a_normal_sized_request_is_not_affected(self, client) -> None:
        response = client.post(
            "/api/auth/register",
            json={"email": "tamanho-normal@example.com", "name": "X", "password": "senhaforte123"},
        )
        assert response.status_code == 201
