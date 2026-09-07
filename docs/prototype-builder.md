# Prototype Builder — Fase 6

## O que é

A primeira camada funcional do Prototype Builder: o usuário cria um
protótipo (nome + descrição), monta uma interface visual simples num
canvas (adicionar/selecionar/editar/remover/reordenar componentes), alterna
entre modo de edição e preview, e salva/recarrega o estado — tudo dentro do
próprio Prospect AI.

Esta fase é deliberadamente uma **fundação**, não o produto final: um
catálogo pequeno de 12 componentes, sem drag-and-drop, sem geração de
código, sem publicação. Ver seção "O que NÃO foi implementado" e
`docs/architecture.md`.

## Autenticação e vínculo com Company (Prompt 10)

Na Fase 6, o Prospect AI ainda não tinha autenticação (confirmado por
auditoria — nenhum JWT/OAuth/sessão em todo o backend até F5), e
`Prototype` não tinha nenhuma referência a `Company`: `owner_id` existia
como uma coluna `String` nunca preenchida, um placeholder para quando
autenticação existisse. A Fase 7 trouxe autenticação real (JWT) e CRM; o
Prompt 10 (antes da geração por IA da Fase 9, que precisa saber de qual
empresa puxar contexto) fechou essa lacuna: `owner_id` foi **removido**
(nunca tinha sido usado para nada) e substituído por `company_id`, uma FK
real para `companies.id`.

**Ownership**: `Prototype` não tem `owner_id` próprio — o acesso é
derivado exatamente como `Contact` já funciona no CRM
(`app.domains.crm.authorization.user_owns_any_opportunity_for_company`):
"este usuário tem uma `Opportunity` para a `Company` deste `Prototype`".
Criar um protótipo exige que o usuário já tenha uma `Opportunity` para a
empresa (`PrototypeService.create` verifica isso antes de persistir,
levantando `LookupError`/`PermissionError`, ambos convertidos em 404 —
nunca 403 — na rota, mesmo padrão de não vazar existência de IDs já usado
em todo o resto do CRM). Ver `app/domains/prototypes/authorization.py`.

**Dado legado**: protótipos criados antes desta migration não têm como
receber um `company_id` real derivado de `owner_id` (que nunca guardou
nada útil) — a coluna aceita `NULL` para não inventar uma empresa falsa
para eles (ver docstring de `models.py` e a migration `0011`). Um
protótipo com `company_id=None` fica permanentemente inacessível pela API
(nenhum usuário pode provar posse de "nenhuma empresa"). Aceitável porque
nenhum ambiente de produção real jamais rodou este projeto.

**Consequência conhecida no frontend**: `POST /api/prototypes` agora
exige `company_id` no payload, mas `NewPrototypeDialog`
(`frontend/src/components/prototype-builder/new-prototype-dialog.tsx`) e
a página `/prototypes` continuam sem nenhum seletor de empresa — criado
como um fluxo standalone na Fase 6, antes de existir qualquer vínculo com
Company. **O botão "Novo protótipo" desta página deixa de funcionar até
uma fase futura adicionar um ponto de entrada com contexto de empresa**
(ex.: a partir da página de uma `Opportunity`/`Company`) — decisão
deliberada de não redesenhar essa UX nesta fase (fora do escopo do Prompt
10, que é estritamente backend), já que a Fase 9 (geração por IA) precisa
resolver exatamente esse fluxo de qualquer forma.

## Modelo de dados

```
Prototype
  id            uuid, pk
  company_id    uuid, FK -> companies.id, nullable só para dado legado (ver acima)
  name          string(200)
  description   string(2000), nullable
  components    JSON — árvore de componentes, ver abaixo
  settings      JSON — configuração do protótipo como um todo
  created_at / updated_at
```

`components` é uma **lista plana** (não uma lista de listas aninhadas):
cada item tem `parent_id` (nulo = raiz) e `order` (posição entre irmãos).
Escolha deliberada em vez da estrutura com `children` aninhado sugerida no
Prompt 09 ("adapte... não copie cegamente"): adicionar, mover ou remover um
nó não exige reescrever a árvore inteira, e a lista plana com `parent_id`
já é suficiente para reconstruir a hierarquia no frontend
(`childrenOf(components, parentId)`).

```
PrototypeComponentInput
  id          string
  type        string — precisa estar em COMPONENT_TYPES (ver Segurança)
  parent_id   string | null
  order       int
  props       dict[str, primitivo curto]
  styles      dict[str, primitivo curto]
```

## Catálogo de componentes (12, seção 4 do Prompt 09)

| Categoria | Componentes |
|---|---|
| Layout | Container, Section, Row, Column |
| Conteúdo | Text, Heading, Button, Image |
| Formulário | Input, Textarea |
| Interface | Card, Divider |

A lista de tipos aceitos (`COMPONENT_TYPES`,
`backend/app/domains/prototypes/schemas.py`) é a **única fonte de
verdade** de validação — o catálogo de renderização do frontend
(`frontend/src/lib/prototype/component-registry.ts`) precisa ser mantido
manualmente em sincronia com ela (mesmo padrão de outras listas
espelhadas no projeto, ex.: `EVIDENCE_FIELD_LABEL`), mas o backend nunca
confia no frontend para essa checagem — rejeita qualquer `type` fora do
catálogo, não importa o que for enviado.

Adicionar um componente novo no futuro é só uma entrada nova nos dois
catálogos — nunca exige mudar a estrutura de `Prototype` (seção 11 do
Prompt 09: arquitetura extensível sem refatoração estrutural).

## Segurança

Três defesas concretas, todas no backend (nunca confiando no frontend):

1. **Catálogo de tipos fechado** (`COMPONENT_TYPES`): qualquer `type` fora
   da lista é rejeitado com `422` antes de qualquer persistência.
2. **`props`/`styles` só aceitam primitivos curtos**
   (`str | int | float | bool | None`, com tamanho e contagem limitados —
   `MAX_PROP_VALUE_LENGTH`, `MAX_PROPS_PER_COMPONENT`). Nenhum objeto
   aninhado, nenhuma lista — isso por si só já impede que um protótipo
   carregue HTML/JavaScript arbitrário como valor de propriedade.
3. **Limites estruturais** (`MAX_COMPONENTS_PER_PROTOTYPE=300`,
   `MAX_TREE_DEPTH=12`), mais detecção de ciclo e de `parent_id`
   pendurado — protegem contra payloads gigantes/profundos como vetor de
   negação de serviço, e contra uma árvore inconsistente ser persistida.

No frontend, `NodeLeafContent`
(`frontend/src/components/prototype-builder/node-renderer.tsx`) **nunca
usa `dangerouslySetInnerHTML`** — todo texto do usuário
(`props.content`, `props.label`, ...) é sempre filho de texto comum do
React, que escapa automaticamente. `<img src>` passa por
`isSafeImageSrc`, que rejeita qualquer esquema que não seja `http:`/
`https:`/caminho relativo — bloqueando `javascript:`/`data:text/html`
mesmo que, em teoria, o atributo já fosse escapado pelo React. Testado
explicitamente em `node-renderer.test.tsx` (conteúdo malicioso aparece
como texto literal, nunca é interpretado; URLs perigosas nunca viram um
`<img>` de verdade).

Nenhum `eval`, nenhuma execução de código do usuário, em nenhum lugar do
Builder — consistente com a seção 10 do Prompt 09.

## Por que Canvas e Preview usam o mesmo renderer

`NodeLeafContent`/`containerClassName`/`containerStyle`
(`node-renderer.tsx`) são chamados tanto pelo `Canvas` em modo `edit`
quanto em modo `preview` — a única diferença é que o modo `edit` envolve
cada nó num wrapper clicável com contorno de seleção, e o `preview` não
adiciona nenhum wrapper. Nunca existe uma segunda implementação da
interface (seção 8 do Prompt 09: "não crie uma segunda implementação
independente").

## Estado do Builder — sem biblioteca nova

Um único `useReducer` (`builder-reducer.ts`), sem Zustand/Redux/Jotai —
não havia nenhuma biblioteca de estado global no projeto antes desta fase,
e a Fase 6 pede explicitamente para não introduzir uma sem necessidade. O
estado cobre: árvore de componentes, seleção, modo (`edit`/`preview`),
histórico de undo/redo e uma flag `dirty`.

**Undo/redo** (seção 13 do Prompt 09: "se a arquitetura permitir facilmente,
adicione") foi implementado — encaixou de forma simples no reducer, como
uma pilha de snapshots da árvore. Edição de propriedade (digitar num campo
de texto) não empilha um snapshot a cada tecla — um único snapshot é
tirado no início de uma "sessão de edição" e a sessão fecha no `onBlur` do
campo (`COMMIT_HISTORY`), evitando inundar o histórico. `Ctrl+Z`/
`Ctrl+Shift+Z` (ou `Ctrl+Y`) funcionam como atalho, além dos botões da
toolbar.

## Arquitetura (seção 11 do Prompt 09)

```
lib/prototype/
  types.ts                — ComponentNode, COMPONENT_TYPES, tipos compartilhados
  component-registry.ts   — catálogo: label, ícone, campos editáveis, defaults

components/prototype-builder/
  builder-reducer.ts       — estado + undo/redo (puro, testável sem DOM)
  node-renderer.tsx        — renderização de UM nó (usado por Canvas e Preview)
  canvas.tsx                — árvore recursiva + seleção
  component-palette.tsx     — lista de componentes disponíveis, adiciona ao clicar
  property-panel.tsx        — campos dinâmicos conforme o tipo selecionado
  toolbar.tsx                — nome, salvar, undo/redo, alternar preview
  prototype-builder.tsx      — compõe os anteriores + Server Action de salvar
  new-prototype-dialog.tsx   — formulário de criação (lista de protótipos)

app/prototypes/
  page.tsx, loading.tsx, error.tsx     — lista
  actions.ts                            — criar/excluir (Server Actions)
  [prototypeId]/
    page.tsx, loading.tsx, error.tsx, not-found.tsx
    actions.ts                          — salvar (Server Action)
```

Mesmo padrão de Server Components + Server Actions da Fase 5
(`docs/dashboard.md`): `lib/api/prototypes.ts` roda só no servidor
(`server-only`), o navegador nunca fala com o backend Python diretamente.

## Persistência

`PUT /api/prototypes/{id}` substitui a árvore de componentes inteira a
cada salvamento — o Builder sempre manda o estado completo, nunca um patch
incremental. Mais simples e determinístico: elimina qualquer divergência
entre o que o editor mostra e o que fica persistido, e evita a
complexidade de resolver conflitos de patches parciais concorrentes (que
esta fase não precisa resolver, já que não há colaboração em tempo real).

## API

```
GET    /api/prototypes/meta/component-types  → catálogo de tipos aceitos (público)
POST   /api/prototypes                        → cria (nome + descrição + company_id)
GET    /api/prototypes                        → lista paginada (só empresas acessíveis)
GET    /api/prototypes/{id}                   → detalhe completo
PUT    /api/prototypes/{id}                   → atualiza (nome/descrição/árvore/settings)
DELETE /api/prototypes/{id}                   → exclui
```

Todas as rotas exigem autenticação (`Authorization: Bearer`, Fase 7),
exceto o catálogo de tipos (Prompt 10) — que não expõe dado de nenhum
usuário, mesmo espírito de `GET /api/crm/pipeline/stages`.

## O que NÃO foi implementado (seção 19 do Prompt 09)

Geração de código, publicação/deploy, domínio personalizado, colaboração em
tempo real, marketplace de componentes, sistema de plugins, histórico
ilimitado, geração de backend/banco de dados pelo usuário, execução de
código arbitrário, design responsivo visual completo, um editor
equivalente ao Figma, e drag-and-drop (deliberadamente adiado — a seção 6
do próprio Prompt 09 permite: "não é obrigatório implementar um editor
visual extremamente avançado... priorize estabilidade"). Adicionar/
selecionar/mover/remover funcionam via clique e botões, cobrindo os
critérios de aceitação sem a complexidade de um sistema de arrastar-e-soltar.

## Testes

**Backend**: `tests/prototypes/test_schemas.py` (a validação da árvore —
catálogo de tipos, ciclos, `parent_id` pendurado, limites de tamanho/
profundidade — a principal defesa de segurança desta fase), `test_service.py`
(CRUD + garantia de que uma atualização inválida nunca persiste
parcialmente) e `test_api.py` (o ciclo de vida completo via HTTP).

**Frontend**: `builder-reducer.test.ts` (toda transição de estado, incluindo
o agrupamento do histórico de undo/redo), `component-registry.test.ts`
(catálogo consistente), `node-renderer.test.tsx` (as três provas de
segurança: texto malicioso nunca vira HTML, `javascript:`/`data:text/html`
nunca viram uma imagem real), `canvas.test.tsx`, `property-panel.test.tsx`,
`component-palette.test.tsx`, `new-prototype-dialog.test.tsx` e
`prototype-builder.test.tsx` (integração dos componentes menores).

## Limitações conhecidas

1. Sem drag-and-drop — adicionar/reorganizar é por clique (ver acima).
2. Sem autenticação/ownership real (ver "Achado crítico" acima) — qualquer
   chamador da API vê e edita qualquer protótipo.
3. `PUT` substitui a árvore inteira a cada salvamento — não há resolução
   de conflito para edição concorrente do mesmo protótipo (sem
   colaboração em tempo real nesta fase, o risco é apenas teórico).
4. Reafirma-se toda limitação já documentada nas Fases 0-5 (sem Docker/
   PostgreSQL/Redis reais nesta máquina).
