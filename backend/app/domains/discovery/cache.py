"""Cache best-effort de páginas de resultado, para evitar chamar a mesma
busca externa repetidamente em um curto intervalo.

Reaproveita o Redis que a fila (app.jobs.queue) já usa — não introduz um
componente novo (arquitetura Fase 1, seção 21: "não introduza um sistema de
cache complexo sem necessidade"). Se o Redis estiver indisponível (como
nesta máquina de desenvolvimento — ver docs/development.md), toda operação
de cache falha silenciosamente e o Discovery segue sem cache: cache é uma
otimização, nunca uma dependência rígida.

Chave determinística por provider + página + parâmetros normalizados da
`DiscoveryQuery`. TTL configurável (`Settings.discovery_cache_ttl_seconds`)
— dados de descoberta ficam "velhos" com o tempo; nunca são reutilizados
indefinidamente como se fossem atuais.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime

from app.core.logging import get_logger
from app.domains.discovery.providers.base import ProviderPage
from app.domains.discovery.schemas import DiscoveryQuery
from app.jobs.queue import get_redis_connection

logger = get_logger(__name__)

_NAMESPACE = "discovery:cache"


def build_cache_key(provider: str, query: DiscoveryQuery, *, page_token: str | None) -> str:
    payload = {
        "provider": provider,
        "page_token": page_token,
        "params": query.model_dump(exclude={"requested_by"}),
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()
    return f"{_NAMESPACE}:{digest}"


def get_cached_page(cache_key: str) -> ProviderPage | None:
    try:
        raw = get_redis_connection().get(cache_key)
    except Exception as exc:  # noqa: BLE001 - cache é best-effort, nunca derruba o Discovery
        logger.debug("discovery_cache_unavailable", operation="get", error_type=exc.__class__.__name__)
        return None

    if raw is None:
        return None

    try:
        data = json.loads(raw)
        from app.domains.discovery.dto import DiscoveredCompany

        results = []
        for item in data["results"]:
            item = dict(item)
            item["collected_at"] = datetime.fromisoformat(item["collected_at"])
            results.append(DiscoveredCompany(**item))

        return ProviderPage(
            results=results,
            raw_result_count=data["raw_result_count"],
            operation=data["operation"],
            fields_requested=data["fields_requested"],
            next_page_token=data["next_page_token"],
        )
    except Exception:  # noqa: BLE001 - cache corrompido/formato antigo: ignora, não quebra
        logger.debug("discovery_cache_corrupt_entry", cache_key=cache_key)
        return None


def set_cached_page(cache_key: str, page: ProviderPage, *, ttl_seconds: int) -> None:
    try:
        payload = {
            "results": [
                {**vars(result), "collected_at": result.collected_at.isoformat()} for result in page.results
            ],
            "raw_result_count": page.raw_result_count,
            "operation": page.operation,
            "fields_requested": page.fields_requested,
            "next_page_token": page.next_page_token,
        }
        get_redis_connection().set(cache_key, json.dumps(payload), ex=ttl_seconds)
    except Exception as exc:  # noqa: BLE001 - cache é best-effort
        logger.debug("discovery_cache_unavailable", operation="set", error_type=exc.__class__.__name__)


__all__ = ["build_cache_key", "get_cached_page", "set_cached_page"]
