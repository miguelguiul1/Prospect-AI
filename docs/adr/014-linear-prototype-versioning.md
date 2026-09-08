# ADR-014: Histórico de `PrototypeVersion` sempre linear; "versão atual" = a mais recente; restaurar = copiar, nunca reescrever

**Status**: Aceita (Prompt 12)

## Contexto

O Prompt 12 pediu `PrototypeVersion` (adiado do Prompt 11 por ADR-012, no
gatilho certo: só faz sentido quando existe um loop de refinamento real
gerando múltiplas versões em sequência). Três perguntas de design
precisavam de uma resposta explícita, não implícita no código:

1. "Versão atual" é sempre a mais recente, ou o usuário pode "ativar" uma
   versão anterior sem apagar as seguintes (rollback vs. checkout)?
2. Restaurar uma versão antiga precisa de um mecanismo dedicado, ou pode
   ser "criar uma versão nova idêntica a uma antiga"?
3. Branching (múltiplos caminhos divergentes de versão) é necessário
   nesta fase?

## Decisão

1. **"Versão atual" = a de maior `version_number` para o `Prototype`,
   sempre.** Não existe um ponteiro separado de "versão ativa"/`is_active`
   — `Prototype.components` é fisicamente igual ao `components` dessa
   versão em todo momento (mantido por
   `app.domains.prototypes.versioning.create_version`, o único lugar que
   cria uma `PrototypeVersion`).
2. **Restaurar cria uma versão NOVA com os mesmos `components` da antiga**
   (`PrototypeVersionService.restore`) — nunca um `UPDATE` na versão
   restaurada, nunca uma exclusão das versões "mais recentes que ela".
   `restored_from_version_number` registra qual foi a origem, só para
   exibição/auditoria.
3. **Sem branching** — `version_number` cresce estritamente por
   `Prototype`, nunca há dois caminhos divergentes. Um histórico sempre
   linear é suficiente para o caso de uso desta fase (comparar e
   restaurar versões passadas); branching exigiria um modelo de dados bem
   mais complexo (uma árvore de versões, não uma lista) sem nenhum
   requisito concreto que o justifique ainda.

## Por que esta combinação, não as alternativas

- Um ponteiro de "versão ativa" separado (permitindo "ativar" uma versão
  antiga sem criar uma nova linha) pareceria mais barato à primeira
  vista, mas quebraria a invariante mais valiosa do sistema inteiro desde
  a Fase 4: **nunca sobrescrever, sempre uma linha nova**. Também
  criaria um estado divergente (`Prototype.components` != a versão de
  maior número) que toda leitura futura precisaria checar explicitamente.
- Um mecanismo de restauração dedicado (ex.: um campo `restored=true` que
  reaproveita a linha antiga) tornaria "quantas vezes esta versão X foi
  restaurada, e quando" impossível de responder sem uma tabela auxiliar —
  copiar para uma linha nova responde isso de graça (basta olhar
  `restored_from_version_number` em cada versão).

## Consequências

- Uma edição manual do Builder (`PUT /api/prototypes/{id}`, Fase 6) NÃO
  cria uma `PrototypeVersion` nesta fase — só geração/refinamento por IA
  e restauração passam por `create_version`. Ver a docstring de
  `PrototypeVersion` (`app/domains/prototypes/models.py`) para a
  consequência prática disso (a lista de versões pode "pular" uma edição
  manual, mas o próximo refinamento ainda enxerga o resultado dela, já
  que sempre lê `Prototype.components`, nunca o `components` da última
  versão rastreada).
- `GenerationRun.based_on_version_number` é um inteiro solto (não uma FK)
  para evitar uma dependência circular entre `prototype_generation_runs`
  e `prototype_versions` — ver comentário no próprio campo.

## Quando reconsiderar

Se um requisito real de produto pedir "comparar dois caminhos de edição
divergentes do mesmo protótipo" (branching de verdade), ou "versionar
toda edição manual também" — nenhum dos dois existe hoje.
