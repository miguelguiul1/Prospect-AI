# ADR-013: Não construir um schema completo de props por tipo de componente agora

**Status**: Aceita — validação mínima e específica implementada agora; schema completo adiado (Prompt 11)

## Contexto

A primeira chamada real à Anthropic API deste projeto revelou um bug
real: o modelo devolveu uma árvore estruturalmente válida (passou
catálogo/ciclos/profundidade) mas usou `props.text` em vez de
`props.content` para `heading`/`button` — a interface real
(`node-renderer.tsx`) só lê `content`, então o texto gerado seria
silenciosamente descartado (substituído pelo placeholder padrão do
Builder, nunca um espaço em branco de verdade).

`validate_component_tree` (Fase 6) valida ESTRUTURA (catálogo fechado,
ciclos, `parent_id`, profundidade/contagem máximas, tipo/tamanho de
valor de prop) — nunca SEMÂNTICA (quais props um tipo específico precisa
ter preenchidas). A pergunta: isso deveria virar um schema Pydantic
completo por tipo de componente agora (`image` exigindo `alt`, `input`
exigindo `inputType` válido, etc. — espelhando o `COMPONENT_REGISTRY` do
frontend campo a campo), ou uma correção mínima e específica para o bug
já observado?

## Decisão

**Implementar agora só a correção mínima e específica** — `text`,
`heading` e `button` exigem `props.content` (string não vazia)
(`MissingRequiredPropError`, `app/domains/prototypes/generation/
validation.py`) — e **adiar um schema completo por tipo** para quando um
SEGUNDO gap real (não hipotético) for observado.

Motivos:

1. **Só uma classe de erro real foi observada até aqui** (chave de
   conteúdo ausente/errada). Um schema completo cobriria casos nunca
   vistos na prática (`image` sem `alt`, `input` com `inputType` fora do
   enum, `button` com `variant` inválido) — código para cenários
   hipotéticos, na contramão da postura consistente deste projeto desde a
   Fase 0 ("não resolva hipóteses, resolva o que foi observado de
   verdade").
2. **O prompt já foi corrigido em paralelo** (seção 3 do system prompt
   agora lista os nomes exatos de prop por tipo) — a correção estrutural
   é a rede de segurança para quando o prompt não for seguido, não a
   única defesa. As duas camadas juntas (prompt melhor + validação
   pontual) já reduzem bastante a chance de recorrência da MESMA classe
   de erro.
3. **A extensão para um schema completo é natural e barata quando
   necessária** — o `COMPONENT_REGISTRY` do frontend já define
   exatamente quais props cada tipo espera; um schema Pydantic
   discriminado por `type` seria uma tradução direta dele, não uma
   invenção do zero. Não há razão para pagar esse custo de manutenção
   antes de um segundo caso real justificar.

## Quando reconsiderar

Na primeira vez que uma SEGUNDA classe de erro real (não hipotética,
observada numa chamada real à Anthropic ou relatada por um usuário do
Builder) aparecer — nesse momento, construir o schema completo por tipo
(discriminated union em `PrototypeComponentInput`, ou uma função de
validação dedicada por `type`) deixa de ser especulativo e passa a ser
justificado por dois casos reais, não um.

## Consequências

- `_check_required_content_prop` (nova, `validation.py`) cobre só
  `text`/`heading`/`button` — não valida `image.alt`, `input.inputType`,
  `textarea.label`, etc. Esses continuam podendo vir ausentes ou com
  nomes de prop inconsistentes sem serem rejeitados.
- Testado em três camadas: unidade (`test_generation_validation.py`),
  serviço de ponta a ponta com o erro exato observado
  (`test_generation_service.py`), e o prompt em si documentando os nomes
  corretos (`test_generation_prompt.py`).
- Confirmado contra a API real: uma segunda chamada real (após a
  correção) gerou uma árvore com `props.content` preenchido corretamente
  nos componentes de texto observados, sem levantar
  `MissingRequiredPropError`.
