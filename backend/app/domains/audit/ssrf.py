"""Proteção contra SSRF (Server-Side Request Forgery).

O Digital Audit é o primeiro estágio do Prospect AI que faz requisições
HTTP para uma URL fornecida por uma fonte externa (o "website" que uma
`Company` reivindica ter) — exatamente o cenário que a arquitetura v0.2
identificou desde a Fase 0 como exigindo proteção obrigatória contra SSRF.

Estratégia: antes de qualquer conexão (a URL inicial e cada redirecionamento
subsequente — ver `app.domains.audit.http_client`), validamos o esquema, a
ausência de credenciais embutidas, e resolvemos o hostname para IP,
rejeitando qualquer endereço privado, loopback, link-local, reservado,
multicast, não especificado ou de faixas adicionais de teste/uso especial.

Limitação conhecida e documentada (não escondida): esta validação acontece
ANTES de cada requisição, mas a conexão HTTP em si é feita pelo hostname,
não pelo IP já validado (sem "IP pinning"). Isso deixa uma janela teórica
de "DNS rebinding" entre a validação e a conexão real, onde um DNS
adversarial poderia resolver para um IP diferente entre as duas consultas.
Mitigar isso por completo exigiria fixar a conexão TCP ao IP validado
(reescrevendo a URL para o IP e ajustando SNI/Host manualmente), o que não
foi implementado nesta fase — ver docs/digital-audit.md, seção
"Limitações". O modelo de ameaça aqui (websites que a própria Discovery já
encontrou como candidatos de empresas reais) tem risco bem menor do que
aceitar URL arbitrária de um usuário anônimo, mas a lacuna é real e fica
registrada para endurecimento futuro.
"""
from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable
from urllib.parse import urlsplit

ALLOWED_SCHEMES = frozenset({"http", "https"})

# Faixas adicionais bloqueadas além do que `ipaddress` já cobre via
# is_private/is_loopback/is_link_local/is_reserved/is_multicast/
# is_unspecified — defesa em profundidade, e mais fácil de auditar/testar
# como uma lista explícita do que confiar só nas properties do stdlib.
_EXTRA_BLOCKED_NETWORKS = tuple(
    ipaddress.ip_network(cidr)
    for cidr in (
        "100.64.0.0/10",  # CGNAT (RFC 6598)
        "192.0.0.0/24",  # atribuições de protocolo IETF (RFC 6890)
        "192.0.2.0/24",  # TEST-NET-1 (RFC 5737)
        "198.18.0.0/15",  # benchmarking entre redes (RFC 2544)
        "198.51.100.0/24",  # TEST-NET-2 (RFC 5737)
        "203.0.113.0/24",  # TEST-NET-3 (RFC 5737)
        "169.254.169.254/32",  # metadata de nuvem (AWS/GCP/Azure) — já
        # coberto por is_link_local, listado explicitamente por clareza.
    )
)

ResolverFn = Callable[[str], list[str]]


class UnsafeURLError(Exception):
    """URL rejeitada pela validação de SSRF. `reason` é um código estável
    (não uma mensagem livre) para permitir que quem chama reaja de forma
    diferenciada (ex.: registrar como `not_checked`, não como `inaccessible`).
    """

    def __init__(self, message: str, *, reason: str) -> None:
        super().__init__(message)
        self.reason = reason


def default_resolve(hostname: str) -> list[str]:
    """Resolve um hostname para a lista de endereços IP (A e AAAA)."""
    infos = socket.getaddrinfo(hostname, None)
    return sorted({info[4][0] for info in infos})


def is_ip_blocked(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    ):
        return True

    # Endereço IPv4 mapeado em IPv6 (::ffff:a.b.c.d) — reavalia o IPv4
    # embutido, senão um bloqueio como 127.0.0.1 poderia escapar disfarçado.
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:
        return is_ip_blocked(mapped)

    return any(ip in network for network in _EXTRA_BLOCKED_NETWORKS)


def validate_url_is_safe(url: str, *, resolver: ResolverFn = default_resolve) -> str:
    """Valida esquema, ausência de credenciais embutidas e endereço(s)
    resolvido(s) de uma URL. Devolve o hostname validado em caso de
    sucesso; levanta `UnsafeURLError` caso contrário.

    Chamada tanto para a URL inicial quanto para cada redirecionamento
    (`app.domains.audit.http_client.fetch_safely`) — nunca confiamos que um
    destino é seguro só porque a URL original era.
    """
    parts = urlsplit(url)

    if parts.scheme not in ALLOWED_SCHEMES:
        raise UnsafeURLError(f"esquema não permitido: {parts.scheme!r}", reason="scheme_not_allowed")

    if not parts.hostname:
        raise UnsafeURLError("URL sem hostname", reason="missing_hostname")

    if parts.username or parts.password:
        raise UnsafeURLError("URL com credenciais embutidas não é permitida", reason="embedded_credentials")

    hostname = parts.hostname

    try:
        literal_ip: ipaddress.IPv4Address | ipaddress.IPv6Address | None = ipaddress.ip_address(hostname)
    except ValueError:
        literal_ip = None

    if literal_ip is not None:
        if is_ip_blocked(literal_ip):
            raise UnsafeURLError(f"endereço IP bloqueado: {literal_ip}", reason="blocked_ip")
        return hostname

    try:
        resolved = resolver(hostname)
    except OSError as exc:
        raise UnsafeURLError(
            f"não foi possível resolver o hostname: {hostname}", reason="dns_resolution_failed"
        ) from exc

    if not resolved:
        raise UnsafeURLError(f"hostname não resolveu para nenhum endereço: {hostname}", reason="dns_no_records")

    for ip_str in resolved:
        ip = ipaddress.ip_address(ip_str)
        if is_ip_blocked(ip):
            raise UnsafeURLError(
                f"hostname resolve para endereço bloqueado: {hostname} -> {ip}", reason="blocked_ip"
            )

    return hostname
