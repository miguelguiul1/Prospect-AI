"""Testes de `app.domains.prototypes.generation.validation` (Fase 9 /
Prompt 11)."""
from __future__ import annotations

import uuid

import pytest

from app.domains.prototypes.context import ContextConfidence, ContextField, PrototypeContext
from app.domains.prototypes.generation.validation import (
    MissingRequiredPropError,
    UnsafeGeneratedContentError,
    find_grounding_warnings,
    validate_generated_tree,
)
from app.domains.prototypes.schemas import validate_component_tree


def _unknown(source: str) -> ContextField:
    return ContextField(value=None, confidence=ContextConfidence.UNKNOWN, source=source)


def _context(**overrides: ContextField) -> PrototypeContext:
    base = dict(
        company_id=uuid.uuid4(),
        context_version="v1",
        company_name=ContextField(value="Padaria Central", confidence=ContextConfidence.FACT, source="company.canonical_name"),
        category=_unknown("company.category"),
        region=_unknown("company.region"),
        site_state=_unknown("audit_snapshot.site_state"),
        website_url=_unknown("audit_snapshot.website_url"),
        phone=_unknown("evidence:phone"),
        address=_unknown("evidence:address"),
        website_title=_unknown("evidence:website_title"),
        website_meta_description=_unknown("evidence:website_meta_description"),
        contact_available=_unknown("evidence:website_contact_available"),
        social_links=_unknown("evidence:website_social_links"),
        opportunity_tier=_unknown("opportunity_score.tier"),
        opportunity_score=_unknown("opportunity_score.score"),
        recommended_product=_unknown("opportunity_score.recommended_product"),
        sales_brief_summary=_unknown("sales_brief.summary"),
        sales_brief_suggested_angle=_unknown("sales_brief.suggested_angle"),
        freshness=None,
    )
    base.update(overrides)
    return PrototypeContext(**base)


def _tree(components: list[dict]) -> list[dict]:
    return components


class TestSchemaReuse:
    def test_valid_tree_passes(self) -> None:
        tree = _tree(
            [{"id": "a", "type": "container", "parent_id": None, "order": 0, "props": {}, "styles": {}}]
        )
        result = validate_generated_tree(tree)
        assert len(result) == 1

    def test_type_outside_catalog_is_rejected(self) -> None:
        tree = _tree([{"id": "a", "type": "script", "parent_id": None, "order": 0}])
        with pytest.raises(ValueError):
            validate_generated_tree(tree)


class TestUrlSafety:
    def test_javascript_scheme_in_image_src_is_rejected(self) -> None:
        tree = _tree(
            [
                {
                    "id": "img",
                    "type": "image",
                    "parent_id": None,
                    "order": 0,
                    "props": {"src": "javascript:alert(1)"},
                    "styles": {},
                }
            ]
        )
        with pytest.raises(UnsafeGeneratedContentError):
            validate_generated_tree(tree)

    def test_data_scheme_is_rejected(self) -> None:
        tree = _tree(
            [
                {
                    "id": "img",
                    "type": "image",
                    "parent_id": None,
                    "order": 0,
                    "props": {"src": "data:text/html,<script>alert(1)</script>"},
                    "styles": {},
                }
            ]
        )
        with pytest.raises(UnsafeGeneratedContentError):
            validate_generated_tree(tree)

    def test_https_url_is_accepted(self) -> None:
        tree = _tree(
            [
                {
                    "id": "img",
                    "type": "image",
                    "parent_id": None,
                    "order": 0,
                    "props": {"src": "https://example.com/foto.jpg"},
                    "styles": {},
                }
            ]
        )
        result = validate_generated_tree(tree)
        assert result[0].props["src"] == "https://example.com/foto.jpg"

    def test_empty_src_placeholder_is_accepted(self) -> None:
        tree = _tree(
            [
                {
                    "id": "img",
                    "type": "image",
                    "parent_id": None,
                    "order": 0,
                    "props": {"placeholder": True},
                    "styles": {},
                }
            ]
        )
        result = validate_generated_tree(tree)
        assert result[0].props["placeholder"] is True

    def test_unsafe_scheme_anywhere_a_url_prop_key_is_used_is_rejected(self) -> None:
        """Não só `image` — `href`/`url`/`link` em QUALQUER componente
        (ex.: button, mesmo que o catálogo hoje não defina um campo de URL
        para ele) são checados, já que `props` não é validado por chave no
        schema."""
        tree = _tree(
            [
                {
                    "id": "btn",
                    "type": "button",
                    "parent_id": None,
                    "order": 0,
                    "props": {"content": "Clique", "href": "javascript:evil()"},
                    "styles": {},
                }
            ]
        )
        with pytest.raises(UnsafeGeneratedContentError):
            validate_generated_tree(tree)


class TestRequiredContentProp:
    """Achado REAL da primeira chamada real à Anthropic API deste
    projeto: o modelo devolveu uma árvore estruturalmente válida (passou
    catálogo/ciclos) mas usou `props.text` em vez de `props.content` para
    heading/button — a interface real só lê `content`, então o texto
    gerado seria silenciosamente descartado. Esta é a rede de segurança
    estrutural para esse caso — não depende só do prompt "pedir certo"."""

    def test_heading_with_wrong_prop_key_is_rejected(self) -> None:
        """A chave errada exata observada na chamada real: `text` em vez
        de `content`."""
        tree = [
            {
                "id": "h1",
                "type": "heading",
                "parent_id": None,
                "order": 0,
                "props": {"text": "Bem-vindo"},
                "styles": {},
            }
        ]
        with pytest.raises(MissingRequiredPropError):
            validate_generated_tree(tree)

    def test_button_with_empty_props_is_rejected(self) -> None:
        tree = [
            {"id": "btn", "type": "button", "parent_id": None, "order": 0, "props": {}, "styles": {}}
        ]
        with pytest.raises(MissingRequiredPropError):
            validate_generated_tree(tree)

    def test_text_with_blank_content_is_rejected(self) -> None:
        tree = [
            {
                "id": "t",
                "type": "text",
                "parent_id": None,
                "order": 0,
                "props": {"content": "   "},
                "styles": {},
            }
        ]
        with pytest.raises(MissingRequiredPropError):
            validate_generated_tree(tree)

    def test_heading_with_correct_content_prop_is_accepted(self) -> None:
        tree = [
            {
                "id": "h1",
                "type": "heading",
                "parent_id": None,
                "order": 0,
                "props": {"content": "Bem-vindo"},
                "styles": {},
            }
        ]
        result = validate_generated_tree(tree)
        assert result[0].props["content"] == "Bem-vindo"

    def test_layout_types_never_require_a_content_prop(self) -> None:
        """container/section/row/column/card/divider não exibem texto —
        nunca devem ser exigidos a ter props.content."""
        tree = [
            {"id": "root", "type": "container", "parent_id": None, "order": 0, "props": {}, "styles": {}},
            {"id": "s", "type": "section", "parent_id": "root", "order": 0, "props": {}, "styles": {}},
            {"id": "d", "type": "divider", "parent_id": "root", "order": 1, "props": {}, "styles": {}},
        ]
        result = validate_generated_tree(tree)
        assert len(result) == 3


class TestGroundingHeuristic:
    def test_phone_number_not_in_context_is_flagged(self) -> None:
        parsed = validate_component_tree(
            [
                {
                    "id": "t",
                    "type": "text",
                    "parent_id": None,
                    "order": 0,
                    "props": {"content": "Ligue para (11) 98765-4321 agora mesmo"},
                    "styles": {},
                }
            ]
        )
        context = _context()  # nenhum telefone conhecido

        warnings = find_grounding_warnings(parsed, context)

        assert len(warnings) == 1
        assert "telefone" in warnings[0]

    def test_phone_number_matching_a_known_fact_is_not_flagged(self) -> None:
        known_phone = "(11) 98765-4321"
        parsed = validate_component_tree(
            [
                {
                    "id": "t",
                    "type": "text",
                    "parent_id": None,
                    "order": 0,
                    "props": {"content": f"Ligue para {known_phone} agora mesmo"},
                    "styles": {},
                }
            ]
        )
        context = _context(
            phone=ContextField(value=known_phone, confidence=ContextConfidence.FACT, source="evidence:phone")
        )

        warnings = find_grounding_warnings(parsed, context)

        assert warnings == []

    def test_generic_ux_copy_without_any_number_is_never_flagged(self) -> None:
        parsed = validate_component_tree(
            [
                {
                    "id": "t",
                    "type": "text",
                    "parent_id": None,
                    "order": 0,
                    "props": {"content": "Fale conosco para saber mais sobre nossos produtos."},
                    "styles": {},
                }
            ]
        )
        context = _context()

        assert find_grounding_warnings(parsed, context) == []

    def test_grounding_warnings_never_block_validation(self) -> None:
        """A heurística nunca é chamada por `validate_generated_tree` —
        avisos são responsabilidade separada do service, nunca bloqueiam
        a persistência."""
        tree = _tree(
            [
                {
                    "id": "t",
                    "type": "text",
                    "parent_id": None,
                    "order": 0,
                    "props": {"content": "Ligue para (11) 98765-4321"},
                    "styles": {},
                }
            ]
        )
        result = validate_generated_tree(tree)  # não levanta, mesmo com um "fato" não fundamentado
        assert len(result) == 1
