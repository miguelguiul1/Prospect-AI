# ADR-012: Não criar `PrototypeVersion` nesta fase

**Status**: Superada — o gatilho abaixo disparou no Prompt 12 (Refinamento
+ Versionamento), que implementou `PrototypeVersion`. Ver
[ADR-014](./014-linear-prototype-versioning.md) para o modelo de dados e
as decisões de design adotadas quando o gatilho disparou.

## Contexto

A auditoria original do Prototype Builder (Prompt 09) e o roadmap da
Fase 9 mencionam versionamento de protótipo (histórico de gerações,
comparação entre versões, capacidade de reverter) como uma capacidade
esperada eventualmente. O Prompt 11 introduziu `GenerationRun` (uma
execução da geração por IA) e `ContextSnapshot` (o contexto usado nessa
execução) — ambos já dão histórico por si só: cada geração é uma linha
nova, nunca sobrescreve a anterior.

A pergunta: isso já é suficiente, ou faltava um terceiro modelo,
`PrototypeVersion`, guardando um snapshot da ÁRVORE DE COMPONENTES
resultante de cada geração/edição, para permitir comparar/reverter entre
versões do protótipo em si (não só reconstruir o contexto de uma geração
específica)?

## Decisão

**Não criar `PrototypeVersion` nesta fase.** Motivos:

1. **Não há loop de refinamento ainda.** `PrototypeVersion` só faz
   sentido de verdade quando existe uma sequência real de edições para
   comparar entre si — hoje, `Prototype.components` é sobrescrito uma
   vez pela primeira geração (ou por uma edição manual via `PUT`, desde
   a Fase 6). Sem o refinamento por linguagem natural (explicitamente a
   próxima fase, não esta), não existe ainda o cenário de "múltiplas
   versões geradas em sequência que alguém precisa comparar".
2. **`GenerationRun` já cobre o caso de uso real de hoje**: "por que a IA
   colocou isso aí" é respondido por `ContextSnapshot` + os metadados do
   próprio `GenerationRun` (prompt_version, provider, model, tokens). O
   que falta para versionamento de verdade — comparar árvore A vs. árvore
   B, reverter para uma árvore anterior — é um problema diferente,
   melhor resolvido junto do loop de refinamento (que vai precisar dessa
   mesma capacidade de qualquer forma).
3. Criar o modelo agora, sem o fluxo que o usaria, seria over-engineering
   — código para um cenário ainda não implementado, na contramão da
   instrução explícita desta fase ("criar agora sem o loop de
   refinamento existir ainda seria overengineering").

## Quando reconsiderar

Na próxima fase (Refinamento + Versionamento, mencionada explicitamente
no Prompt 11 como o que vem depois) — nesse momento, `PrototypeVersion`
(ou nome equivalente) se torna necessário para: guardar cada árvore de
componentes intermediária gerada pelo refinamento, permitir comparar/
reverter entre elas, e decidir se cada refinamento cria uma versão nova
ou edita a atual. `GenerationRun`/`ContextSnapshot` continuam existindo
sem mudança — são sobre a GERAÇÃO (o processo de chamar a IA), não sobre
o RESULTADO versionado (a árvore em si), então não competem com um
`PrototypeVersion` futuro.

## Consequências

- Nenhum modelo novo nesta fase além de `GenerationRun`/`ContextSnapshot`.
- Uma segunda geração para o mesmo `Prototype` (fora de escopo desta
  fase — nada na API atual chama `/generate` duas vezes para o mesmo
  protótipo em um fluxo normal) sobrescreveria `Prototype.components`
  sem guardar a árvore anterior — aceitável porque não há ainda nenhum
  fluxo de produto que provoque isso deliberadamente.
