"""Extração de sinais técnicos da página principal de um website.

Usa `html.parser.HTMLParser` (biblioteca padrão do Python) — nunca executa
JavaScript, nunca interpreta CSS, nunca segue `<script>`/`<iframe>`. HTML é
tratado estritamente como texto a ser tokenizado, nunca como instrução
(arquitetura Fase 3, seção 15: conteúdo de terceiro é dado, não comando).

Só a página inicial é analisada — nenhum link é seguido a partir daqui
(isso seria crawling, fora do escopo desta fase; ver seção 7 do prompt).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from app.domains.discovery.normalization import UNTRUSTED_WEBSITE_DOMAINS, extract_hostname

_PHONE_PATTERN = re.compile(r"(\+?\d[\d\s().-]{7,}\d)")
_CONTACT_WORDS = ("contato", "contact", "fale conosco", "atendimento")

_HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}


@dataclass
class HtmlSignals:
    title: str | None = None
    meta_description: str | None = None
    canonical: str | None = None
    viewport_present: bool = False
    language: str | None = None
    robots_meta_blocking: bool = False
    favicon_present: bool = False

    heading_count: int = 0
    h1_count: int = 0
    text_length: int = 0

    image_count: int = 0
    images_with_alt: int = 0

    form_present: bool = False

    internal_link_count: int = 0
    external_link_count: int = 0
    social_links: list[str] = field(default_factory=list)

    phone_like_text_found: bool = False
    contact_link_found: bool = False

    @property
    def image_alt_ratio(self) -> float | None:
        if self.image_count == 0:
            return None
        return self.images_with_alt / self.image_count


class _SignalExtractor(HTMLParser):
    def __init__(self, *, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self._base_url = base_url
        self._base_host = extract_hostname(base_url)
        self.signals = HtmlSignals()

        self._in_title = False
        self._in_script_or_style = False
        self._current_text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_dict = {key: (value or "") for key, value in attrs}
        tag = tag.lower()

        if tag == "title":
            self._in_title = True
        elif tag in ("script", "style"):
            self._in_script_or_style = True
        elif tag == "meta":
            self._handle_meta(attr_dict)
        elif tag == "link":
            self._handle_link(attr_dict)
        elif tag == "html":
            lang = attr_dict.get("lang")
            if lang:
                self.signals.language = lang
        elif tag in _HEADING_TAGS:
            self.signals.heading_count += 1
            if tag == "h1":
                self.signals.h1_count += 1
        elif tag == "img":
            self.signals.image_count += 1
            if attr_dict.get("alt", "").strip():
                self.signals.images_with_alt += 1
        elif tag == "form":
            self.signals.form_present = True
        elif tag == "a":
            self._handle_anchor(attr_dict)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "title":
            self._in_title = False
        elif tag in ("script", "style"):
            self._in_script_or_style = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            current = (self.signals.title or "") + data
            self.signals.title = current.strip()
            return

        if self._in_script_or_style:
            return  # nunca conta conteúdo de <script>/<style> como texto ou o interpreta

        stripped = data.strip()
        if stripped:
            self.signals.text_length += len(stripped)
            if not self.signals.phone_like_text_found and _PHONE_PATTERN.search(stripped):
                self.signals.phone_like_text_found = True
            lowered = stripped.lower()
            if not self.signals.contact_link_found and any(word in lowered for word in _CONTACT_WORDS):
                self.signals.contact_link_found = True

    def _handle_meta(self, attrs: dict[str, str]) -> None:
        name = attrs.get("name", "").lower()
        content = attrs.get("content", "")

        if name == "description" and not self.signals.meta_description:
            self.signals.meta_description = content.strip()
        elif name == "viewport":
            self.signals.viewport_present = True
        elif name == "robots" and "noindex" in content.lower():
            self.signals.robots_meta_blocking = True
        elif name in ("language", "content-language") and not self.signals.language:
            self.signals.language = content.strip()
        elif attrs.get("http-equiv", "").lower() == "content-language" and not self.signals.language:
            self.signals.language = content.strip()

    def _handle_link(self, attrs: dict[str, str]) -> None:
        rel = attrs.get("rel", "").lower()
        href = attrs.get("href", "")

        if "canonical" in rel and href:
            self.signals.canonical = urljoin(self._base_url, href)
        elif "icon" in rel:
            self.signals.favicon_present = True

    def _handle_anchor(self, attrs: dict[str, str]) -> None:
        href = attrs.get("href", "").strip()
        if not href:
            return

        if href.startswith("tel:"):
            self.signals.phone_like_text_found = True
            return
        if href.startswith("mailto:"):
            self.signals.contact_link_found = True
            return
        if href.startswith(("#", "javascript:")):
            return

        absolute = urljoin(self._base_url, href)
        parts = urlsplit(absolute)
        if parts.scheme not in ("http", "https"):
            return

        host = extract_hostname(absolute)

        if host in UNTRUSTED_WEBSITE_DOMAINS:
            if absolute not in self.signals.social_links:
                self.signals.social_links.append(absolute)
            return

        if host == self._base_host:
            self.signals.internal_link_count += 1
        else:
            self.signals.external_link_count += 1


def extract_html_signals(html: str, *, base_url: str) -> HtmlSignals:
    """Extrai sinais técnicos de uma página HTML.

    `html` já deve ter sido decodificado como texto (ver
    `app.domains.audit.service`, que decide o encoding a partir do header
    `Content-Type` com fallback seguro). Nunca levanta exceção por HTML
    malformado — `HTMLParser` da biblioteca padrão já é tolerante a isso;
    qualquer erro inesperado é responsabilidade de quem chama tratar.
    """
    parser = _SignalExtractor(base_url=base_url)
    parser.feed(html)
    parser.close()
    return parser.signals
