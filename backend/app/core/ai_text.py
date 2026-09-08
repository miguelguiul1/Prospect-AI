"""Utilitário compartilhado de limpeza de saída de provider de IA.

Achado real (Prompt 11 — a primeira chamada real à Anthropic API já feita
neste projeto, depois de todo o desenvolvimento ter usado só providers
fake/mockados): apesar da instrução explícita "responda apenas com JSON,
sem markdown, nada antes ou depois" presente em TODO prompt deste projeto
que pede saída estruturada (Sales Brief, Assisted Outreach, Prototype
Generation), o modelo real por vezes envolve a resposta em um bloco de
código Markdown (` ```json ... ``` `) mesmo assim — um comportamento que
nenhum `FakeProvider`/`FakeGenerationProvider` jamais revelaria, já que
sempre devolvem JSON limpo por construção. Sem isto, `json.loads` falha
com `Expecting value: line 1 column 1 (char 0)` (o primeiro caractere é
uma crase, não `{`) — nunca um bug de parsing nosso, um comportamento real
do provider que precisa ser tolerado na borda de entrada, não "corrigido"
só insistindo mais na instrução do prompt (que já pede exatamente isso).
"""
from __future__ import annotations

import re

_CODE_FENCE_RE = re.compile(r"^```(?:[a-zA-Z0-9_+-]*)?\s*\n?(.*?)\n?```$", re.DOTALL)


def strip_markdown_code_fence(text: str) -> str:
    """Remove um bloco de código Markdown que envolva o texto INTEIRO (do
    início ao fim, com ou sem uma tag de linguagem como `json`) — nunca
    tenta extrair um bloco de código em meio a texto livre ao redor dele,
    porque isso mascararia uma resposta que genuinamente não seguiu o
    formato pedido (melhor deixar essa resposta falhar a validação de
    verdade do que aceitar algo que veio com prosa antes/depois).

    Texto sem cerca de código é devolvido inalterado (só com espaços nas
    bordas removidos).
    """
    stripped = text.strip()
    match = _CODE_FENCE_RE.match(stripped)
    if match:
        return match.group(1).strip()
    return stripped


__all__ = ["strip_markdown_code_fence"]
