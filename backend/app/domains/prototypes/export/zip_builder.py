"""Empacotamento do export estático em `.zip` (Prompt 15).

Gerado sob demanda, em memória, a cada chamada — nunca persistido em
disco/storage (o conteúdo é determinístico a partir de
`PrototypeVersion.components`, então não há necessidade de cache; ver
seção 3 do Prompt 15 sobre essa decisão)."""
from __future__ import annotations

import io
import re
import zipfile

from app.domains.prototypes.export.renderer import render_prototype_export
from app.domains.prototypes.models import Prototype, PrototypeVersion

_README_TEMPLATE = """# {name} — export estático

Este é um export estático (HTML + CSS) de uma versão do protótipo
"{name}", gerado pelo Prospect AI.

## O que este arquivo é

- `index.html` e `styles.css`: um site estático simples, sem
  interatividade além do que HTML/CSS puro oferece. Elementos como
  formulários são exibidos visualmente, mas não enviam dados para
  lugar nenhum — para isso, você precisaria de um backend próprio.
- Não há JavaScript, não há framework, não há build necessário.

## Como hospedar

Qualquer serviço de hospedagem de arquivos estáticos serve. Alguns
exemplos comuns (o Prospect AI não tem integração com nenhum deles —
você mesmo cria a conta e faz o upload):

- **Netlify**: arraste a pasta extraída para netlify.com/drop.
- **Vercel**: `vercel deploy` a partir desta pasta (requer a CLI da
  Vercel instalada).
- **Qualquer servidor próprio**: copie `index.html` e `styles.css` para
  a raiz pública do seu servidor web (Apache, Nginx, etc.).

## Gerado em

Protótipo: {name}
Versão: {version_number}
"""

_SAFE_FILENAME_CHARS = re.compile(r"[^a-zA-Z0-9\-]+")


def export_filename(prototype: Prototype, version: PrototypeVersion) -> str:
    """Nome de arquivo seguro para o header `Content-Disposition` — nunca
    interpola `prototype.name` (texto livre do usuário) sem sanitizar:
    sem isso, um nome com aspas/CRLF poderia quebrar o header HTTP."""
    slug = _SAFE_FILENAME_CHARS.sub("-", prototype.name).strip("-").lower() or "prototipo"
    return f"{slug}-v{version.version_number}.zip"


def build_export_zip(prototype: Prototype, version: PrototypeVersion) -> bytes:
    site = render_prototype_export(version.components, title=prototype.name)
    readme = _README_TEMPLATE.format(name=prototype.name, version_number=version.version_number)

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("index.html", site.html)
        archive.writestr("styles.css", site.css)
        archive.writestr("README.md", readme)
    return buffer.getvalue()


__all__ = ["build_export_zip", "export_filename"]
