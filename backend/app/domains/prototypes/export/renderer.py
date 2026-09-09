"""Gerador de HTML/CSS estático a partir de uma árvore de componentes já
validada (Prompt 15 — Export de Código Estático).

Transformação puramente determinística — nunca gera React/JS executável,
nunca chama IA, nunca executa nada do que está armazenado. `props`/
`styles` só carregam primitivos curtos (`schemas.py`), e o frontend nunca
os trata como HTML/CSS bruto (`node-renderer.tsx`); este módulo replica o
MESMO comportamento visual em HTML/CSS puro.

Tratado como uma SEGUNDA camada de defesa (a árvore já passou pela
validação de catálogo/URL do Prompt 11 ao ser persistida — ver
`generation/validation.py` e `schemas.py`), não como confiança cega no que
já está no banco:

- Reaproveita `validate_component_tree` aqui de novo (nunca confia que um
  `PrototypeVersion.components` já persistido continua estruturalmente
  válido sem reconferir).
- Todo texto (`props.content`/`label`/`placeholder`/`alt`) passa por
  `html.escape(..., quote=True)` antes de entrar no HTML — nunca
  interpolado cru, mesmo que a validação anterior já devesse ter barrado
  conteúdo malicioso.
- `props.src` de imagem é reconferido aqui (mesmas regras de
  `_check_url_safety`), nunca assumido seguro só porque já passou uma vez.
- Valores de `styles.color` (a única prop que vira CSS livre, não HTML)
  passam por um allowlist de sintaxe antes de entrar em `styles.css` —
  sem isso, um valor como `red; } body { display:none } .x {` quebraria
  para fora da regra CSS pretendida.
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass

from app.domains.prototypes.schemas import PrototypeComponentInput, validate_component_tree

_CONTAINER_TYPES = frozenset({"container", "section", "row", "column", "card"})
_SAFE_URL_PREFIXES = ("http://", "https://", "/")

_TAG_BY_CONTAINER_TYPE = {
    "container": "div",
    "section": "section",
    "row": "div",
    "column": "div",
    "card": "div",
}
_EXTRA_CLASS_BY_TYPE = {
    "row": "row",
    "column": "column",
    "card": "card",
}

_ALIGN_VALUES = frozenset({"left", "center", "right"})
_INPUT_TYPES = frozenset({"text", "email", "number"})
_BUTTON_VARIANTS = frozenset({"primary", "secondary", "outline"})

# Allowlist de sintaxe para `styles.color` — nunca interpolado sem checar,
# porque (diferente de texto em HTML) uma string de cor vira CSS livre, e
# `html.escape` não protege contra quebrar para fora de uma regra CSS.
_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{3,8}$")
_NAMED_COLOR = re.compile(r"^[a-zA-Z]{3,20}$")
_FUNC_COLOR = re.compile(r"^(rgb|rgba|hsl|hsla|oklch)\([0-9.,%\s/]{1,60}\)$")
_WEIGHT_VALUE = re.compile(r"^[0-9]{3}$")


@dataclass(frozen=True)
class ExportedSite:
    html: str
    css: str


def render_prototype_export(raw_components: list[dict], *, title: str) -> ExportedSite:
    """Ponto de entrada único do módulo. `raw_components` é a lista plana
    (mesmo formato de `Prototype.components`/`PrototypeVersion.components`)."""
    nodes = validate_component_tree(raw_components)

    by_parent: dict[str | None, list[PrototypeComponentInput]] = {}
    for node in nodes:
        by_parent.setdefault(node.parent_id, []).append(node)
    for children in by_parent.values():
        children.sort(key=lambda n: n.order)

    css_rules: list[str] = []
    class_counter = {"n": 0}

    def next_class() -> str:
        name = f"node-{class_counter['n']}"
        class_counter["n"] += 1
        return name

    def render_node(node: PrototypeComponentInput, depth: int) -> str:
        indent = "  " * depth
        class_name = next_class()
        rule = _css_rule(class_name, node.styles, node_type=node.type)
        if rule:
            css_rules.append(rule)

        if node.type in _CONTAINER_TYPES:
            children = by_parent.get(node.id, [])
            tag = _TAG_BY_CONTAINER_TYPE[node.type]
            extra = _EXTRA_CLASS_BY_TYPE.get(node.type, "")
            classes = f"{class_name} {extra}".strip()
            if not children:
                return f'{indent}<{tag} class="{classes}"></{tag}>'
            inner = "\n".join(render_node(child, depth + 1) for child in children)
            return f'{indent}<{tag} class="{classes}">\n{inner}\n{indent}</{tag}>'

        return f"{indent}{_render_leaf(node, class_name)}"

    roots = by_parent.get(None, [])
    body = "\n".join(render_node(root, 1) for root in roots)

    document = _HTML_TEMPLATE.format(title=_escape(title), body=body)
    stylesheet = _BASE_CSS + ("\n\n" + "\n".join(css_rules) if css_rules else "")
    return ExportedSite(html=document, css=stylesheet)


def _render_leaf(node: PrototypeComponentInput, class_name: str) -> str:
    if node.type == "text":
        return f'<p class="{class_name}">{_escape(_str(node.props.get("content"), "Texto de exemplo"))}</p>'

    if node.type == "heading":
        return f'<h3 class="{class_name}">{_escape(_str(node.props.get("content"), "Título"))}</h3>'

    if node.type == "button":
        variant = _str(node.props.get("variant"), "primary")
        if variant not in _BUTTON_VARIANTS:
            variant = "primary"
        content = _escape(_str(node.props.get("content"), "Clique aqui"))
        return f'<span class="{class_name} btn btn-{variant}" role="button">{content}</span>'

    if node.type == "image":
        src = _str(node.props.get("src"))
        if not _is_safe_image_src(src):
            # Nunca inventa URL/imagem — mesmo placeholder visual que o
            # Builder mostra (`node-renderer.tsx`, "Sem imagem").
            return f'<div class="{class_name} img">Sem imagem</div>'
        alt = _escape(_str(node.props.get("alt")))
        return f'<img class="{class_name} img" src="{_escape(src)}" alt="{alt}">'

    if node.type == "input":
        label = _str(node.props.get("label"))
        placeholder = _escape(_str(node.props.get("placeholder")))
        input_type = _str(node.props.get("inputType"), "text")
        if input_type not in _INPUT_TYPES:
            input_type = "text"
        label_html = f"<span>{_escape(label)}</span>" if label else ""
        return (
            f'<label class="{class_name} field">{label_html}'
            f'<input type="{input_type}" placeholder="{placeholder}" disabled></label>'
        )

    if node.type == "textarea":
        label = _str(node.props.get("label"))
        placeholder = _escape(_str(node.props.get("placeholder")))
        label_html = f"<span>{_escape(label)}</span>" if label else ""
        return (
            f'<label class="{class_name} field">{label_html}'
            f'<textarea rows="3" placeholder="{placeholder}" disabled></textarea></label>'
        )

    if node.type == "divider":
        return f'<hr class="{class_name}">'

    # Inalcançável: `validate_component_tree` já rejeita qualquer `type`
    # fora de `COMPONENT_TYPES`, e todos os demais são containers
    # (tratados antes de chegar aqui).
    raise AssertionError(f"tipo de componente folha desconhecido: {node.type}")


def _css_rule(class_name: str, styles: dict, *, node_type: str) -> str:
    declarations: list[str] = []

    padding = styles.get("padding")
    if isinstance(padding, (int, float)) and not isinstance(padding, bool):
        declarations.append(f"padding: {padding}px;")

    gap = styles.get("gap")
    if isinstance(gap, (int, float)) and not isinstance(gap, bool):
        declarations.append(f"gap: {gap}px;")

    width = styles.get("width")
    if isinstance(width, (int, float)) and not isinstance(width, bool):
        declarations.append(f"width: {width}px;")

    height = styles.get("height")
    if isinstance(height, (int, float)) and not isinstance(height, bool):
        declarations.append(f"height: {height}px;")

    align = styles.get("align")
    if isinstance(align, str) and align in _ALIGN_VALUES:
        declarations.append(f"text-align: {align};")

    weight = styles.get("weight")
    if isinstance(weight, str) and _WEIGHT_VALUE.match(weight):
        declarations.append(f"font-weight: {weight};")

    color = styles.get("color")
    if isinstance(color, str) and _is_safe_css_color(color):
        declarations.append(f"color: {color};")

    if not declarations:
        return ""
    return f".{class_name} {{ {' '.join(declarations)} }}"


def _is_safe_css_color(value: str) -> bool:
    if len(value) > 64:
        return False
    return bool(_HEX_COLOR.match(value) or _NAMED_COLOR.match(value) or _FUNC_COLOR.match(value))


def _is_safe_image_src(src: str) -> bool:
    if not src:
        return False
    return src.startswith(_SAFE_URL_PREFIXES)


def _str(value: object, fallback: str = "") -> str:
    return value if isinstance(value, str) else fallback


def _escape(text: str) -> str:
    """Sempre `quote=True`: mesma função usada tanto para texto de
    elemento quanto para valor de atributo — escapar aspas em texto puro
    é inofensivo (`"` vira `&quot;`, renderiza igual), e usar uma única
    função em todo lugar evita o risco de esquecer o escape certo em um
    contexto de atributo por engano."""
    return html.escape(text, quote=True)


_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <link rel="stylesheet" href="styles.css">
</head>
<body>
<main class="page">
{body}
</main>
</body>
</html>
"""

# Estilos de base (tags/classes compartilhadas) — os tokens de cor abaixo
# espelham o tema claro real do Prototype Builder (`frontend/src/app/
# globals.css`), para que o export fique visualmente próximo do preview
# real sem precisar embarcar Tailwind (fora de escopo desta fase — ver
# seção 6 do relatório sobre limites de fidelidade, ex.: sem modo escuro).
_BASE_CSS = """:root {
  --background: oklch(1 0 0);
  --foreground: oklch(0.18 0.006 264);
  --card: oklch(1 0 0);
  --primary: oklch(0.47 0.2 264);
  --primary-foreground: oklch(0.98 0 0);
  --secondary: oklch(0.97 0.004 264);
  --secondary-foreground: oklch(0.28 0.03 264);
  --muted: oklch(0.97 0.004 264);
  --muted-foreground: oklch(0.5 0.015 264);
  --border: oklch(0.91 0.006 264);
}

* { box-sizing: border-box; }

body {
  margin: 0;
  background: var(--background);
  color: var(--foreground);
  font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
  line-height: 1.5;
}

.page { display: flex; flex-direction: column; gap: 12px; padding: 24px; max-width: 960px; margin: 0 auto; }

.row { display: flex; flex-direction: row; flex-wrap: wrap; gap: 12px; }
.column { display: flex; flex-direction: column; gap: 12px; }
.card { border-radius: 12px; border: 1px solid var(--border); background: var(--card); box-shadow: 0 1px 2px rgb(0 0 0 / 5%); }

.btn { display: inline-flex; align-items: center; border-radius: 6px; padding: 6px 12px; font-size: 14px; font-weight: 500; text-decoration: none; cursor: default; border: 1px solid transparent; }
.btn-primary { background: var(--primary); color: var(--primary-foreground); }
.btn-secondary { background: var(--secondary); color: var(--secondary-foreground); }
.btn-outline { background: transparent; color: var(--foreground); border-color: var(--border); }

.field { display: flex; flex-direction: column; gap: 4px; font-size: 14px; }
.field input, .field textarea { border-radius: 6px; border: 1px solid var(--border); background: var(--background); color: var(--foreground); padding: 6px 10px; font: inherit; }

.img { width: 240px; height: 160px; }
img.img { object-fit: cover; border-radius: 6px; }
div.img { display: flex; align-items: center; justify-content: center; border-radius: 6px; border: 1px dashed var(--border); background: var(--muted); color: var(--muted-foreground); font-size: 12px; }

hr { border: none; border-top: 1px solid var(--border); margin: 0; }
"""


__all__ = ["ExportedSite", "render_prototype_export"]
