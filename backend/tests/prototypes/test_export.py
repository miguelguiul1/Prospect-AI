"""Testes do export estático (Prompt 15).

`TestRenderer*`/`TestZipBuilder` exercitam o gerador puro, sem HTTP.
`TestExportEndpoint` exercita `GET /api/prototypes/{id}/versions/{id}/
export` de ponta a ponta (autorização + resposta binária real)."""
from __future__ import annotations

import io
import uuid
import zipfile
from html.parser import HTMLParser

import pytest

from app.domains.audit.enums import AuditStatus
from app.domains.audit.models import AuditSnapshot
from app.domains.companies.models import Company
from app.domains.prototypes.export.renderer import render_prototype_export
from app.domains.prototypes.export.zip_builder import build_export_zip, export_filename
from app.domains.prototypes.models import Prototype, PrototypeVersion

# Void elements que este renderer emite sem tag de fechamento — mesma
# lista do HTML5 real, restrita aos tipos que o catálogo pode produzir.
_VOID_TAGS = frozenset({"hr", "img", "input", "meta", "link"})


class _StackValidatingParser(HTMLParser):
    """Prova real de "parseável e sem tags quebradas": empilha cada tag de
    abertura (exceto void elements) e desempilha no fechamento
    correspondente — qualquer divergência (fechamento sem abertura,
    abertura nunca fechada) levanta `AssertionError` explícito."""

    def __init__(self) -> None:
        super().__init__()
        self.stack: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:  # noqa: ANN001
        if tag not in _VOID_TAGS:
            self.stack.append(tag)

    def handle_endtag(self, tag: str) -> None:
        assert self.stack, f"tag de fechamento </{tag}> sem abertura correspondente"
        top = self.stack.pop()
        assert top == tag, f"esperava fechar <{top}>, encontrei </{tag}>"


def _assert_well_formed_html(document: str) -> None:
    parser = _StackValidatingParser()
    parser.feed(document)
    parser.close()
    assert parser.stack == [], f"tags nunca fechadas: {parser.stack}"


def _tree_with_one_of_each() -> list[dict]:
    """Uma árvore pequena, mas com pelo menos um de cada categoria de
    tipo (container-com-filhos, folha de texto, folha de formulário,
    imagem) — o suficiente para exercitar cada ramo do renderer."""
    return [
        {"id": "root", "type": "section", "parent_id": None, "order": 0, "props": {}, "styles": {"padding": 24}},
        {"id": "row1", "type": "row", "parent_id": "root", "order": 0, "props": {}, "styles": {"gap": 12}},
        {
            "id": "h1",
            "type": "heading",
            "parent_id": "row1",
            "order": 0,
            "props": {"content": "Bem-vindo"},
            "styles": {"weight": "700"},
        },
        {
            "id": "t1",
            "type": "text",
            "parent_id": "row1",
            "order": 1,
            "props": {"content": "Um parágrafo de exemplo."},
            "styles": {"align": "left"},
        },
        {
            "id": "btn1",
            "type": "button",
            "parent_id": "row1",
            "order": 2,
            "props": {"content": "Fale conosco", "variant": "primary"},
            "styles": {},
        },
        {"id": "card1", "type": "card", "parent_id": "root", "order": 1, "props": {}, "styles": {"padding": 16}},
        {
            "id": "img1",
            "type": "image",
            "parent_id": "card1",
            "order": 0,
            "props": {"placeholder": True},
            "styles": {"width": 200, "height": 120},
        },
        {
            "id": "in1",
            "type": "input",
            "parent_id": "card1",
            "order": 1,
            "props": {"label": "E-mail", "placeholder": "voce@exemplo.com", "inputType": "email"},
            "styles": {},
        },
        {
            "id": "ta1",
            "type": "textarea",
            "parent_id": "card1",
            "order": 2,
            "props": {"label": "Mensagem", "placeholder": "Escreva aqui..."},
            "styles": {},
        },
        {"id": "div1", "type": "divider", "parent_id": "card1", "order": 3, "props": {}, "styles": {}},
    ]


class TestRendererOutput:
    def test_produces_well_formed_html_for_a_known_tree(self) -> None:
        site = render_prototype_export(_tree_with_one_of_each(), title="Padaria Central")

        _assert_well_formed_html(site.html)
        assert "<title>Padaria Central</title>" in site.html
        assert 'href="styles.css"' in site.html

    def test_every_component_type_produces_recognizable_output(self) -> None:
        site = render_prototype_export(_tree_with_one_of_each(), title="t")

        assert "<section" in site.html
        assert "Bem-vindo" in site.html and "<h3" in site.html
        assert "Um parágrafo de exemplo." in site.html and "<p" in site.html
        assert "Fale conosco" in site.html and "btn-primary" in site.html
        assert "<label class=" in site.html and 'field">' in site.html
        assert "<textarea" in site.html
        assert "<hr" in site.html

    def test_css_is_a_separate_stylesheet_not_inlined_per_element(self) -> None:
        site = render_prototype_export(_tree_with_one_of_each(), title="t")

        assert "style=" not in site.html, "estilo não deveria ser inline no HTML"
        assert "padding: 24px;" in site.css
        assert "gap: 12px;" in site.css
        assert "font-weight: 700;" in site.css


class TestContentEscaping:
    """Seção 2 do Prompt 15: mesmo a árvore já tendo passado pela
    validação do Prompt 11, a geração de HTML escapa tudo de novo."""

    def test_script_tag_in_text_content_is_escaped_not_executed(self) -> None:
        malicious = '<script>alert(1)</script>'
        components = [
            {
                "id": "t1",
                "type": "text",
                "parent_id": None,
                "order": 0,
                "props": {"content": malicious},
                "styles": {},
            }
        ]

        site = render_prototype_export(components, title="t")

        assert "<script>" not in site.html
        assert "&lt;script&gt;" in site.html
        _assert_well_formed_html(site.html)

    def test_attribute_breaking_quote_in_button_content_is_escaped(self) -> None:
        malicious = '"><img src=x onerror=alert(1)>'
        components = [
            {
                "id": "b1",
                "type": "button",
                "parent_id": None,
                "order": 0,
                "props": {"content": malicious},
                "styles": {},
            }
        ]

        site = render_prototype_export(components, title="t")

        assert "onerror=alert(1)>" not in site.html
        assert "&quot;&gt;&lt;img" in site.html
        _assert_well_formed_html(site.html)

    def test_malicious_color_style_cannot_break_out_of_the_css_rule(self) -> None:
        components = [
            {
                "id": "t1",
                "type": "text",
                "parent_id": None,
                "order": 0,
                "props": {"content": "x"},
                "styles": {"color": "red; } body { display: none } .x { color: red"},
            }
        ]

        site = render_prototype_export(components, title="t")

        assert "display: none" not in site.css
        assert "color:" not in site.css or "color: red;" not in site.css


class TestImagePlaceholder:
    def test_image_marked_as_placeholder_renders_a_visual_placeholder_never_a_url(self) -> None:
        components = [
            {"id": "i1", "type": "image", "parent_id": None, "order": 0, "props": {"placeholder": True}, "styles": {}}
        ]

        site = render_prototype_export(components, title="t")

        assert "<img" not in site.html
        assert "Sem imagem" in site.html

    def test_image_with_unsafe_src_also_falls_back_to_placeholder(self) -> None:
        """Defesa em profundidade: `PrototypeService.update` (edição manual
        via PUT) só roda `validate_component_tree` — NUNCA a checagem de
        segurança de URL (`generation/validation.py`, só usada na geração
        por IA). Sem esta reconferência aqui, uma edição manual poderia
        persistir `javascript:` e o export o interpolaria cru."""
        components = [
            {
                "id": "i1",
                "type": "image",
                "parent_id": None,
                "order": 0,
                "props": {"src": "javascript:alert(1)"},
                "styles": {},
            }
        ]

        site = render_prototype_export(components, title="t")

        assert "javascript:" not in site.html
        assert "<img" not in site.html
        assert "Sem imagem" in site.html

    def test_image_with_safe_src_renders_a_real_img_tag(self) -> None:
        components = [
            {
                "id": "i1",
                "type": "image",
                "parent_id": None,
                "order": 0,
                "props": {"src": "https://example.com/photo.jpg", "alt": "Foto"},
                "styles": {},
            }
        ]

        site = render_prototype_export(components, title="t")

        assert '<img class="node-0 img" src="https://example.com/photo.jpg" alt="Foto">' in site.html


class TestZipBuilder:
    def _prototype_and_version(self, name: str = "Padaria Central & Cia") -> tuple[Prototype, PrototypeVersion]:
        prototype = Prototype(id=uuid.uuid4(), name=name, components=[], settings={})
        version = PrototypeVersion(
            id=uuid.uuid4(), prototype_id=prototype.id, version_number=3, components=_tree_with_one_of_each()
        )
        return prototype, version

    def test_zip_contains_exactly_the_expected_files_and_is_valid(self) -> None:
        prototype, version = self._prototype_and_version()

        raw = build_export_zip(prototype, version)

        archive = zipfile.ZipFile(io.BytesIO(raw))
        assert archive.testzip() is None
        assert set(archive.namelist()) == {"index.html", "styles.css", "README.md"}
        assert b"<!DOCTYPE html>" in archive.read("index.html")
        assert b"padding" in archive.read("styles.css")
        assert b"Padaria Central" in archive.read("README.md")

    def test_filename_is_sanitized_from_free_text_prototype_name(self) -> None:
        prototype, version = self._prototype_and_version(name='Site "top" <do cliente> / v2')

        filename = export_filename(prototype, version)

        assert filename.endswith(".zip")
        assert all(c.isalnum() or c == "-" or c == "." for c in filename)
        assert "v3" in filename


def _headers(client, email: str = "vendedor@example.com") -> dict:
    token = client.post(
        "/api/auth/register", json={"email": email, "name": "Vendedor", "password": "senhaforte123"}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _company_with_context(db, name: str = "Padaria Central") -> Company:
    company = Company(canonical_name=name)
    db.add(company)
    db.flush()
    db.add(AuditSnapshot(company_id=company.id, run_id=uuid.uuid4(), status=AuditStatus.COMPLETED))
    db.flush()
    db.commit()
    return company


def _prototype_with_version(client, db, headers) -> tuple[str, str]:
    """Cria Company + Opportunity (acesso) + Prototype + uma
    PrototypeVersion real (via PUT, que já é validado/versionado neste
    projeto só indiretamente — aqui criamos a versão direto no banco,
    mais simples que passar pelo fluxo de geração por IA só para ter uma
    versão para exportar). Retorna (prototype_id, version_id)."""
    company = _company_with_context(db)
    client.post("/api/crm/opportunities", json={"company_id": str(company.id)}, headers=headers)
    created = client.post(
        "/api/prototypes", json={"name": "Site da Padaria", "company_id": str(company.id)}, headers=headers
    ).json()
    prototype_id = created["id"]

    prototype = db.get(Prototype, uuid.UUID(prototype_id))
    version = PrototypeVersion(
        prototype_id=prototype.id, version_number=1, components=_tree_with_one_of_each()
    )
    db.add(version)
    prototype.components = version.components
    db.commit()
    return prototype_id, str(version.id)


class TestExportEndpoint:
    def test_export_returns_a_valid_zip_with_the_expected_content_type(self, client, db_session) -> None:
        headers = _headers(client)
        prototype_id, version_id = _prototype_with_version(client, db_session, headers)

        response = client.get(
            f"/api/prototypes/{prototype_id}/versions/{version_id}/export", headers=headers
        )

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/zip"
        assert "attachment;" in response.headers["content-disposition"]

        archive = zipfile.ZipFile(io.BytesIO(response.content))
        assert archive.testzip() is None
        assert set(archive.namelist()) == {"index.html", "styles.css", "README.md"}

    def test_export_without_token_is_unauthorized(self, client, db_session) -> None:
        headers = _headers(client)
        prototype_id, version_id = _prototype_with_version(client, db_session, headers)

        response = client.get(f"/api/prototypes/{prototype_id}/versions/{version_id}/export")
        assert response.status_code == 401

    def test_export_for_a_prototype_i_dont_have_access_to_returns_404(self, client, db_session) -> None:
        owner_headers = _headers(client, "dono@example.com")
        prototype_id, version_id = _prototype_with_version(client, db_session, owner_headers)

        other_headers = _headers(client, "outro@example.com")
        response = client.get(
            f"/api/prototypes/{prototype_id}/versions/{version_id}/export", headers=other_headers
        )
        assert response.status_code == 404

    def test_export_of_a_nonexistent_version_returns_404(self, client, db_session) -> None:
        headers = _headers(client)
        company = _company_with_context(db_session)
        client.post("/api/crm/opportunities", json={"company_id": str(company.id)}, headers=headers)
        created = client.post(
            "/api/prototypes", json={"name": "Site", "company_id": str(company.id)}, headers=headers
        ).json()

        response = client.get(
            f"/api/prototypes/{created['id']}/versions/{uuid.uuid4()}/export", headers=headers
        )
        assert response.status_code == 404
