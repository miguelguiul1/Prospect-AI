from __future__ import annotations

from app.core.config import Settings


def test_settings_load_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("LOG_LEVEL", "WARNING")

    settings = Settings()

    assert settings.app_env == "production"
    assert settings.log_level == "WARNING"
    assert settings.is_production is True


def test_settings_never_default_a_real_secret() -> None:
    """Nenhuma chave de API de fase futura pode ter um valor default não
    nulo — isso garantiria que uma credencial real nunca seja acidentalmente
    versionada como "default" do código."""
    settings = Settings()

    assert settings.google_maps_api_key is None
    assert settings.google_custom_search_api_key is None
    assert settings.google_custom_search_cx is None
    assert settings.instagram_graph_access_token is None
    assert settings.anthropic_api_key is None
    assert settings.discovery_cost_per_request is None


def test_settings_default_environment_is_development(monkeypatch) -> None:
    # conftest.py define APP_ENV=test para isolar o banco de teste; aqui
    # removemos a variável para exercitar o default real do campo.
    monkeypatch.delenv("APP_ENV", raising=False)

    settings = Settings(_env_file=None)

    assert settings.app_env == "development"
