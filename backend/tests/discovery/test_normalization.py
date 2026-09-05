from __future__ import annotations

from app.domains.discovery.normalization import (
    normalize_address,
    normalize_category,
    normalize_name,
    normalize_phone,
    normalize_url,
    normalize_whitespace,
)


def test_normalize_whitespace_collapses_and_strips() -> None:
    assert normalize_whitespace("  Restaurante   São\tJoão  ") == "Restaurante São João"


def test_normalize_name_returns_none_for_blank() -> None:
    assert normalize_name("   ") is None
    assert normalize_name(None) is None


def test_normalize_address_only_cleans_whitespace() -> None:
    assert normalize_address("Rua A, 123  -  Centro") == "Rua A, 123 - Centro"


def test_normalize_category_lowercases_and_replaces_underscores() -> None:
    assert normalize_category("italian_restaurant") == "italian restaurant"


def test_normalize_phone_to_e164() -> None:
    assert normalize_phone("(11) 2345-6789") == "+551123456789"


def test_normalize_phone_accepts_already_international_format() -> None:
    assert normalize_phone("+55 11 91234-5678") == "+5511912345678"


def test_normalize_phone_returns_none_for_garbage() -> None:
    assert normalize_phone("not-a-phone") is None
    assert normalize_phone(None) is None


def test_normalize_url_adds_https_scheme() -> None:
    assert normalize_url("empresa.com.br") == "https://empresa.com.br"


def test_normalize_url_strips_trailing_slash() -> None:
    assert normalize_url("https://empresa.com.br/") == "https://empresa.com.br"


def test_normalize_url_lowercases_host_only() -> None:
    assert normalize_url("https://Empresa.COM.BR/Contato") == "https://empresa.com.br/Contato"


def test_normalize_url_returns_none_for_invalid_value() -> None:
    assert normalize_url("   ") is None
    assert normalize_url(None) is None
