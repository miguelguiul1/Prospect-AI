# Refinamento por Linguagem Natural + Versionamento — Prompt 12

## O que é um "refinamento" neste sistema

Um refinamento é uma instrução em linguagem natural do usuário (ex.:
"deixa mais premium e destaca o botão de WhatsApp") aplicada sobre um
`Prototype` que já tem **pelo menos um `GenerationRun` com
`status=SUCCEEDED`** — nunca sobre um protótipo que nunca foi gerado por
IA (`NoPreviousVersionError`, ver "Precondição" abaixo). O resultado é
sempre uma `PrototypeVersion` NOVA — nunca uma edição in-place da versão
anterior, mesmo princípio de "nunca sobrescrever, sempre uma linha nova"
usado por `SalesBrief`/`GenerationRun` desde a Fase 4.

## Reaproveitar ou renovar o `PrototypeContext`?

**Decisão: sempre renovar.** `PrototypeContextBuilder.build()` roda de
novo a cada refinamento, exatamente como na geração inicial — nenhum
atalho para reaproveitar o `ContextSnapshot` de uma geração anterior.

Isso diverge da expectativa original da auditoria (Prompt 12, citando a
seção 25: "a expectativa é reaproveitar o contexto existente [...] para
evitar regenerar tudo do zero"). A divergência é deliberada:
`PrototypeContextBuilder.build()` é uma consulta ao PRÓPRIO banco
(Company/Evidence/AuditSnapshot/OpportunityScore/SalesBrief) — **zero
custo de IA, zero chamada de rede paga**. O único custo real de um
refinamento é a chamada ao provider de IA, que acontece de qualquer forma
independente de reaproveitar ou renovar o contexto. O motivo original
para "reaproveitar" (economizar) não se aplica: renovar é estritamente
melhor pelo mesmo custo (contexto sempre atualizado, caso a Evidence
tenha mudado desde a última geração).

## Precondição e "árvore atual"

- **Precondição** (`NoPreviousVersionError`): existe pelo menos um
  `GenerationRun` com `status=SUCCEEDED` para este `Prototype`. Uma
  geração que FALHOU não conta.
- **"Árvore atual" enviada ao prompt de refinamento**: sempre
  `Prototype.components` no momento da execução — nunca o `components`
  da última `PrototypeVersion` rastreada. Isso importa porque uma edição
  manual do Builder (`PUT`, Fase 6) NÃO cria uma `PrototypeVersion`
  nesta fase (ver "Versionamento" abaixo) — se ela acontecer depois da
  última geração/refinamento, `Prototype.components` já reflete essa
  edição, e é isso que o próximo refinamento efetivamente vê e edita.
- `GenerationRun.based_on_version_number` registra qual era a
  `PrototypeVersion` mais recente NESTE momento, só para auditoria — não
  necessariamente byte-a-byte o que foi enviado ao provider, pelo motivo
  acima.

## `PrototypeVersion`

Ver [ADR-014](./adr/014-linear-prototype-versioning.md) para a decisão
completa. Resumo:

- **Histórico sempre linear** — `version_number` cresce estritamente por
  `Prototype`, sem branching.
- **"Versão atual" = a de maior `version_number`, sempre.** Não existe um
  ponteiro separado de "versão ativa". `Prototype.components` é mantido
  fisicamente igual a essa versão por
  `app.domains.prototypes.versioning.create_version` — o ÚNICO lugar que
  cria uma `PrototypeVersion` (chamado por `PrototypeGenerationService`
  na geração/refinamento, e por `PrototypeVersionService.restore`).
- **Restaurar = criar uma versão nova idêntica à antiga**
  (`restored_from_version_number` registra qual) — preferido a um
  mecanismo de rollback dedicado, mais simples e consistente com o
  histórico linear.
- **Limitação documentada, deliberada**: uma edição manual via `PUT` NÃO
  cria uma `PrototypeVersion` — versionar toda tecla do editor manual
  estava fora do escopo desta fase (o pedido é sobre refinamento por IA +
  histórico dessas gerações). A lista de versões pode "pular" uma edição
  manual, mas o refinamento seguinte ainda a respeita (ver seção
  anterior).

Migration `0013_prototype_versioning`: uma tabela nova
(`prototype_versions`) + três colunas novas em
`prototype_generation_runs` (`instruction`, `based_on_version_number`,
`diff_summary`), todas nullable — testada com `alembic upgrade head` +
`--autogenerate` (diff vazio, confirma que a migration reflete
`models.py` exatamente) e com o roundtrip completo de
`tests/test_migrations_roundtrip.py`.

## Refinement Loop

```
Instrução do usuário (texto livre)
          +
Árvore de componentes atual (Prototype.components)
          +
PrototypeContext (sempre renovado)
          ↓
     Generation Engine (MESMO motor do Prompt 11 —
     PrototypeGenerationService.start()/execute(), sem
     segundo pipeline; só o prompt muda)
          ↓
     Mesma validação em camadas do Prompt 11
     (validate_generated_tree + find_grounding_warnings,
     reaproveitadas sem alteração)
          ↓
     Nova PrototypeVersion (create_version)
```

`app.domains.prototypes.generation.prompt.REFINEMENT_SYSTEM_PROMPT`/
`build_refinement_prompt` é um prompt SEPARADO (não uma variação
parametrizada do de geração inicial) — mesma decisão já tomada por
`briefing`/`outreach` (cada fluxo mantém seu próprio texto fixo e
revisável). Três blocos delimitados no `user prompt`, cada um com um
papel diferente e claramente comunicado ao modelo:

1. `<CONTEXTO_NAO_CONFIAVEL>` — dados da empresa, mesmo tratamento do
   Prompt 11 (nunca instrução, mesmo se parecer um comando).
2. `<ARVORE_ATUAL>` — a árvore JSON atual, gerada por este mesmo sistema
   anteriormente (também dado, nunca instrução).
3. `<PEDIDO_DO_USUARIO>` — a instrução do usuário autenticado: uma
   instrução LEGÍTIMA sobre O QUE mudar (ao contrário do bloco 1), mas
   que nunca autoriza violar a regra de grounding nem as regras de
   formato/catálogo/props.

Os quatro marcadores de delimitação (`_DATA_OPEN/_CLOSE`,
`_TREE_OPEN/_CLOSE`, `_INSTRUCTION_OPEN/_CLOSE`) são neutralizados em
QUALQUER um dos três blocos por uma única `_neutralize()` generalizada —
não só no bloco de dados original — para que um marcador literal em
qualquer um deles nunca consiga "fechar" um bloco prematuramente.

### Mudança mínima: incentivar (prompt) + medir (diff)

A instrução do Prompt 12 pediu para decidir como medir/incentivar que um
refinamento altere só o que foi pedido, mesmo que de forma aproximada:

- **Incentivar**: regra explícita no `REFINEMENT_SYSTEM_PROMPT` ("MUDANÇA
  MÍNIMA" — todo componente sem relação com o pedido permanece
  EXATAMENTE como está).
- **Medir**: `app.domains.prototypes.generation.diffing.
  summarize_component_diff(before, after)` compara as duas árvores por
  `id` (adicionados/removidos/alterados) e calcula `changed_ratio`,
  persistido em `GenerationRun.diff_summary` — só para refinamento (a
  geração inicial não tem "antes" real para comparar).

**Limitação documentada**: nenhuma das duas garante mudança mínima — um
modelo pode ignorar a regra do prompt e reescrever componentes sem
relação com o pedido, e nada aqui impede isso automaticamente. `
diff_summary` só torna o tamanho da mudança visível para revisão humana
depois, mesma filosofia não-bloqueante de `find_grounding_warnings`.

## Grounding: o que fazer quando o próprio usuário pede um fato inventado

**A regra mais importante do projeto (nunca inventar um FACT/SIGNAL
ausente) não é enfraquecida pelo refinamento.** Decisão explícita,
documentada aqui e no `REFINEMENT_SYSTEM_PROMPT` (não resolvida
silenciosamente de um jeito ou de outro):

Se o usuário pedir algo como "diz que atendemos 24 horas" e isso não
estiver marcado FACT/SIGNAL no `PrototypeContext`, o modelo:

- **NUNCA inclui o fato específico pedido** — usa uma alternativa
  genérica de marketing (ex.: "Fale conosco", "Atendimento
  personalizado") ou simplesmente não atende essa parte do pedido;
- **sempre atende o restante do pedido normalmente** — nunca falha o
  refinamento inteiro por causa disso.

Por que não recusar o refinamento inteiro, nem classificar a intenção do
usuário para decidir "bloquear ou não": a maioria de um pedido de
refinamento é sobre estilo/layout/copy genérico, não sobre fatos —
recusar tudo seria desproporcional. Classificar a intenção exigiria uma
SEGUNDA chamada de IA só para essa decisão, custo/complexidade
desproporcional para esta fase. A defesa continua em duas camadas
não-bloqueantes, mesmo padrão de todo o projeto desde a Fase 4: a regra
explícita do prompt, e `find_grounding_warnings` (heurística já existente
do Prompt 11, reaproveitada sem alteração) sinalizando para revisão
humana caso algo que parece um fato específico apareça mesmo assim.
Testado em `tests/prototypes/test_refinement_service.py::
TestRefinementGroundingViolation` — simula exatamente esse cenário
(pedido de "24 horas" + telefone inventado) e confirma que o grounding
warning aparece, sem bloquear o refinamento.

## API

```
POST /api/prototypes/{id}/refine                          → aplica um refinamento (202, mesmo formato de /generate)
GET  /api/prototypes/{id}/versions                         → lista o histórico, mais recente primeiro
GET  /api/prototypes/{id}/versions/{version_id}            → detalhe de uma versão (árvore completa)
POST /api/prototypes/{id}/versions/{version_id}/restore    → cria uma versão nova idêntica à antiga
```

Mesma autorização de qualquer rota de `Prototype` (só quem tem
`Opportunity` para a empresa). Mesmo limite de "uma geração em andamento
por vez" (`GenerationInProgressError`) para `/refine` — e também para
`/restore`, por precaução contra uma corrida entre uma geração terminando
e uma restauração concorrente.

## Cost control

Refinamentos contam para o MESMO limite diário de geração já existente do
Prompt 11 (`prototype_generation_rate_limit_max_per_day`,
`fail_closed`) — `/generate` e `/refine` usam exatamente a mesma chave de
rate limit (`_check_prototype_generation_rate_limit`, extraída para
garantir que os dois pontos de chamada nunca divirjam na formatação da
chave). Restaurar uma versão NUNCA chama IA — sem custo, sem rate limit.

## Frontend

- **Refinamento**: `RefinementBar` (dentro do Prototype Builder) — um
  campo de texto + botão "Aplicar" com estado de carregamento, NUNCA um
  chat com histórico de mensagens (fora de escopo, seção 6/7 do
  Prompt 12). Em sucesso, despacha `LOAD` no reducer do Builder para
  substituir a árvore pela versão nova sem recarregar a página; avisos de
  grounding aparecem inline.
- **Versões**: `/prototypes/{id}/versions` lista o histórico (data,
  descrição curta derivada da instrução ou "Geração inicial por IA"/
  "Restaurado da versão N"); `/prototypes/{id}/versions/{versionId}`
  mostra um preview somente-leitura (`VersionPreview`, reaproveita
  `Canvas` em modo preview) com um botão "Restaurar esta versão".

## Não implementado nesta fase (fora de escopo, por instrução explícita)

- Branching de versões.
- Chat com histórico de conversa (o refinamento é sempre um pedido único
  e independente, sem contexto de mensagens anteriores).
- Preview responsivo (desktop/tablet/mobile).
- Export/deploy/publicação.
- Versionamento de edição manual via `PUT` (ver limitação documentada
  acima).
