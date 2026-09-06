"""Testes de proteção contra SSRF. Nenhum acesso de rede real — DNS é
sempre injetado via o parâmetro `resolver`.
"""
from __future__ import annotations

import pytest

from app.domains.audit.ssrf import UnsafeURLError, is_ip_blocked, validate_url_is_safe
import ipaddress


def _resolver(mapping: dict[str, list[str]]):
    def _resolve(hostname: str) -> list[str]:
        return mapping.get(hostname, [])

    return _resolve


class TestSchemeAndFormat:
    def test_rejects_non_http_scheme(self) -> None:
        with pytest.raises(UnsafeURLError) as exc_info:
            validate_url_is_safe("ftp://example.com/", resolver=_resolver({"example.com": ["93.184.216.34"]}))
        assert exc_info.value.reason == "scheme_not_allowed"

    def test_rejects_missing_hostname(self) -> None:
        with pytest.raises(UnsafeURLError) as exc_info:
            validate_url_is_safe("http:///path")
        assert exc_info.value.reason == "missing_hostname"

    def test_rejects_embedded_credentials(self) -> None:
        with pytest.raises(UnsafeURLError) as exc_info:
            validate_url_is_safe(
                "http://user:pass@example.com/", resolver=_resolver({"example.com": ["93.184.216.34"]})
            )
        assert exc_info.value.reason == "embedded_credentials"

    def test_accepts_safe_public_url(self) -> None:
        hostname = validate_url_is_safe("https://example.com/page", resolver=_resolver({"example.com": ["93.184.216.34"]}))
        assert hostname == "example.com"


class TestDirectIpLiterals:
    @pytest.mark.parametrize(
        "url",
        [
            "http://127.0.0.1/",
            "http://127.0.0.5/",
            "http://0.0.0.0/",
            "http://169.254.169.254/",  # metadata de nuvem
            "http://10.0.0.1/",
            "http://172.16.0.1/",
            "http://192.168.1.1/",
            "http://[::1]/",
            "http://[fe80::1]/",
        ],
    )
    def test_blocks_dangerous_ip_literals(self, url: str) -> None:
        with pytest.raises(UnsafeURLError) as exc_info:
            validate_url_is_safe(url)
        assert exc_info.value.reason == "blocked_ip"

    def test_allows_public_ip_literal(self) -> None:
        hostname = validate_url_is_safe("http://93.184.216.34/")
        assert hostname == "93.184.216.34"


class TestHostnameResolution:
    def test_blocks_hostname_resolving_to_loopback(self) -> None:
        with pytest.raises(UnsafeURLError) as exc_info:
            validate_url_is_safe("http://localhost/", resolver=_resolver({"localhost": ["127.0.0.1"]}))
        assert exc_info.value.reason == "blocked_ip"

    def test_blocks_hostname_resolving_to_private_network(self) -> None:
        """Cenário central de SSRF via DNS: um hostname público na
        aparência que na verdade resolve para uma rede interna."""
        with pytest.raises(UnsafeURLError) as exc_info:
            validate_url_is_safe(
                "http://internal.attacker.example/", resolver=_resolver({"internal.attacker.example": ["10.0.0.5"]})
            )
        assert exc_info.value.reason == "blocked_ip"

    def test_blocks_if_any_resolved_address_is_blocked(self) -> None:
        """DNS pode devolver múltiplos endereços (A/AAAA) — basta UM ser
        privado para bloquear, mesmo que outro seja público."""
        with pytest.raises(UnsafeURLError):
            validate_url_is_safe(
                "http://mixed.example.com/",
                resolver=_resolver({"mixed.example.com": ["93.184.216.34", "127.0.0.1"]}),
            )

    def test_blocks_when_dns_resolution_fails(self) -> None:
        def _raise(hostname: str) -> list[str]:
            raise OSError("nome não encontrado")

        with pytest.raises(UnsafeURLError) as exc_info:
            validate_url_is_safe("http://doesnotexist.example/", resolver=_raise)
        assert exc_info.value.reason == "dns_resolution_failed"

    def test_blocks_when_dns_returns_no_records(self) -> None:
        with pytest.raises(UnsafeURLError) as exc_info:
            validate_url_is_safe("http://empty.example.com/", resolver=_resolver({}))
        assert exc_info.value.reason == "dns_no_records"

    def test_allows_hostname_resolving_to_public_address(self) -> None:
        hostname = validate_url_is_safe(
            "https://www.example.com/", resolver=_resolver({"www.example.com": ["93.184.216.34"]})
        )
        assert hostname == "www.example.com"


class TestExtraBlockedRanges:
    @pytest.mark.parametrize(
        "ip",
        [
            "100.64.0.1",  # CGNAT
            "192.0.2.1",  # TEST-NET-1
            "198.18.0.1",  # benchmarking
            "198.51.100.1",  # TEST-NET-2
            "203.0.113.1",  # TEST-NET-3
        ],
    )
    def test_blocks_special_use_ranges(self, ip: str) -> None:
        assert is_ip_blocked(ipaddress.ip_address(ip)) is True

    def test_does_not_block_ordinary_public_ip(self) -> None:
        assert is_ip_blocked(ipaddress.ip_address("93.184.216.34")) is False

    def test_blocks_ipv4_mapped_ipv6_loopback(self) -> None:
        assert is_ip_blocked(ipaddress.ip_address("::ffff:127.0.0.1")) is True


class TestRedirectRevalidation:
    def test_each_hop_must_be_validated_independently(self) -> None:
        """Não é papel deste módulo seguir redirects — é papel de
        `app.domains.audit.http_client.fetch_safely` chamar esta validação
        de novo a cada hop. Aqui só confirmamos que chamar a validação duas
        vezes, uma para cada URL de um redirecionamento, bloqueia a
        segunda quando ela aponta para um destino interno."""
        first_hostname = validate_url_is_safe(
            "https://public.example.com/", resolver=_resolver({"public.example.com": ["93.184.216.34"]})
        )
        assert first_hostname == "public.example.com"

        with pytest.raises(UnsafeURLError):
            validate_url_is_safe(
                "http://internal.example.com/admin", resolver=_resolver({"internal.example.com": ["192.168.0.1"]})
            )
