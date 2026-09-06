"""Configuração centralizada da aplicação.

Todo segredo/API key vem exclusivamente de variáveis de ambiente — nunca de
um valor default neste arquivo. Ver `.env.example` na raiz do repositório
para a lista completa de variáveis suportadas.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: Literal["development", "test", "production"] = "development"
    app_name: str = "Prospect AI"
    log_level: str = "INFO"

    database_url: str = "postgresql+psycopg://prospect:prospect@localhost:5432/prospect_ai"
    redis_url: str = "redis://localhost:6379/0"

    cors_allow_origins: list[str] = ["http://localhost:3000"]

    # --- Discovery (Fase 1) -------------------------------------------------
    # Nome pedido explicitamente pelo prompt de implementação da Fase 1
    # (substitui o placeholder `google_places_api_key` da Fase 0, que nunca
    # chegou a ser lido por código nenhum).
    google_maps_api_key: str | None = None

    # Provider ativo por padrão quando a busca não especifica um. Só
    # "google_places" está implementado nesta fase — ver
    # app/domains/discovery/providers/__init__.py.
    discovery_provider: str = "google_places"

    # Timeouts e retry são obrigatórios para qualquer chamada externa (ver
    # docs/discovery.md) e configuráveis para não exigir deploy para ajustar.
    discovery_http_connect_timeout_seconds: float = 5.0
    discovery_http_read_timeout_seconds: float = 10.0
    discovery_http_max_retries: int = 3
    discovery_http_backoff_base_seconds: float = 0.5
    discovery_http_backoff_max_seconds: float = 8.0

    # Atraso opcional antes de usar um nextPageToken. A API legada do Google
    # Places exigia um pequeno intervalo após emitir o token; não confirmamos
    # se a API New ainda exige isso (ver docs/discovery.md) — o padrão é 0
    # (sem espera) e fica configurável para quem observar erros de paginação.
    discovery_page_token_delay_seconds: float = 0.0

    # Limites internos (nossos, não do provedor) para impedir que um único
    # SearchRun gere uma quantidade ilimitada de chamadas externas.
    discovery_max_results_hard_cap: int = 60
    discovery_max_pages_hard_cap: int = 3

    # Custo é uma configuração explícita do operador, nunca um valor fixo no
    # código (preços de API mudam e variam por SKU/contrato). Quando None,
    # nenhum custo é estimado — apenas a contagem de chamadas é registrada.
    discovery_cost_per_request: float | None = None
    discovery_cost_currency: str = "USD"

    # Cache best-effort de resultados de busca, reaproveitando o Redis já
    # usado pela fila (não introduz um novo componente). Se o Redis estiver
    # indisponível, o cache é ignorado silenciosamente — nunca derruba a
    # aplicação (ver app/domains/discovery/cache.py).
    discovery_cache_ttl_seconds: int = 86400

    # --- Identity Resolution (Fase 2) ---------------------------------------
    # Limiares de similaridade (0-100, RapidFuzz token_sort_ratio) usados como
    # SINAIS DE APOIO — nunca são suficientes sozinhos para um merge
    # automático (ver app/domains/identity/matching.py e docs/
    # identity-resolution.md). São hipóteses iniciais calibradas manualmente
    # contra os casos de exemplo da Fase 2, não um resultado de dados reais —
    # arquitetura v0.2 já previa que precisariam de recalibração futura.
    identity_name_similarity_threshold: int = 75
    identity_address_similarity_threshold: int = 85
    # Distância (metros) abaixo da qual duas localizações são consideradas
    # "próximas" — nunca suficiente sozinha (empresas diferentes podem
    # dividir prédio/galeria).
    identity_geo_proximity_meters: float = 150.0

    # --- Reservado para integrações de fases futuras -----------------------
    # Nenhum destes campos é lido por qualquer código da Fase 0 ou 1. Eles
    # existem para que a configuração de fases futuras (Digital Audit, Sales
    # Brief) não exija reestruturar o carregamento de settings.
    google_custom_search_api_key: str | None = None
    google_custom_search_cx: str | None = None
    instagram_graph_access_token: str | None = None
    anthropic_api_key: str | None = None
    # -------------------------------------------------------------------

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
