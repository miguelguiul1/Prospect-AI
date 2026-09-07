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

    # --- Digital Audit (Fase 3) ---------------------------------------------
    # Timeouts e limites são obrigatórios para qualquer requisição a um
    # website de terceiro — ver docs/digital-audit.md, seção "Segurança".
    audit_http_connect_timeout_seconds: float = 5.0
    audit_http_read_timeout_seconds: float = 10.0
    audit_http_max_retries: int = 1
    audit_http_backoff_base_seconds: float = 0.5
    audit_http_backoff_max_seconds: float = 4.0

    # Limite nosso, não do site auditado — nunca inflado por um redirect
    # encadeado indefinidamente.
    audit_http_max_redirects: int = 5
    # 2 MB é generoso para uma página HTML de homepage; conteúdo além disso
    # é truncado, nunca usado para inferir "site ruim" automaticamente.
    audit_http_max_response_bytes: int = 2_000_000

    # Identifica o auditor perante o site de terceiro — nunca finge ser um
    # navegador comum. Sem contato real configurado; operadores devem
    # substituir por algo com um e-mail/URL de contato antes de auditar em
    # produção (mesma prática de identificação usada por crawlers legítimos).
    audit_http_user_agent: str = "ProspectAI-DigitalAudit/1.0"

    # --- Sales Brief (Fase 4) -----------------------------------------------
    # Único componente de todo o Prospect AI que chama um provider de IA — ver
    # app.domains.briefing. Sem `anthropic_api_key`, o provider responde
    # `ProviderUnavailableError` de forma controlada (o Opportunity Score
    # continua funcionando normalmente); nenhuma chamada é feita sem a chave.
    anthropic_api_key: str | None = None
    # Modelo é configurável pelo operador (não fixado aqui como verdade
    # absoluta) — confira o identificador de modelo atual na documentação da
    # Anthropic antes de configurar em produção. Ver docs/sales-brief.md.
    anthropic_model: str = "claude-sonnet-4-5-20250929"
    anthropic_api_base_url: str = "https://api.anthropic.com"
    anthropic_http_connect_timeout_seconds: float = 5.0
    anthropic_http_read_timeout_seconds: float = 30.0
    anthropic_max_tokens: int = 1500

    # --- Autenticação (Fase 7) -----------------------------------------------
    # Estratégia definida pelo ADR-001 da auditoria F7.0: JWT próprio (sem
    # provedor gerenciado externo), consistente com a postura do projeto de
    # não adicionar dependência de terceiro além do estritamente necessário.
    # O default abaixo é INSEGURO DE PROPÓSITO (só serve para dev/teste sem
    # `.env`) — a aplicação agora RECUSA subir com este valor quando
    # `APP_ENV=production` (fail-fast, ver `app.main`, Fase 8.3). Antes desta
    # fase, era só um log de aviso — não impedia produção de subir insegura.
    jwt_secret_key: str = "dev-insecure-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60 * 24  # 24h

    # Rate limiting (Fase 7, políticas diferenciadas na Fase 8.3) —
    # reaproveita o Redis já configurado. Login: proteção contra força
    # bruta (fallback local quando Redis está fora do ar — nunca nega login
    # por completo). Register: mesma proteção, evita enumeração/abuso em
    # massa de criação de conta. Outreach/Sales Brief: controle de custo de
    # IA (fail-closed quando Redis está fora do ar — nunca permite chamada
    # ilimitada à Anthropic).
    auth_login_rate_limit_max_attempts: int = 10
    auth_login_rate_limit_window_seconds: int = 300
    auth_register_rate_limit_max_attempts: int = 5
    auth_register_rate_limit_window_seconds: int = 3600
    outreach_rate_limit_max_per_day: int = 20
    sales_brief_rate_limit_max_per_day: int = 20

    # --- Assisted Outreach (Fase 7) ------------------------------------------
    # Reaproveita o mesmo provider/config de IA do Sales Brief
    # (`anthropic_api_key`/`anthropic_model` acima) — só o limite de tokens é
    # menor, porque uma mensagem de outreach é bem mais curta que um briefing.
    outreach_max_tokens: int = 700

    # --- Security hardening (Fase 8.3) ----------------------------------------
    # Nenhum endpoint aceita um corpo de requisição maior que isto — protege
    # contra consumo de memória/banda por payload gigante antes mesmo da
    # validação Pydantic (achado R7 da auditoria F8.0). 1 MB é generoso para
    # qualquer payload real do sistema (o maior campo de texto único é
    # limitado a 4000 caracteres).
    max_request_body_bytes: int = 1_000_000

    # --- Reservado para integrações de fases futuras -----------------------
    # Nenhum destes campos é lido por qualquer código das Fases 0-7.
    google_custom_search_api_key: str | None = None
    google_custom_search_cx: str | None = None
    instagram_graph_access_token: str | None = None
    # Provedores de envio real de Outreach (Nível 2, F7.7+ futuro) — apenas
    # reservados, nunca lidos nesta fase (Assisted Outreach não envia nada).
    email_provider_api_key: str | None = None
    whatsapp_provider_api_key: str | None = None
    # -------------------------------------------------------------------

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
