# Dashboard — Fase 5

## O que é

O Dashboard é a primeira interface visual do Prospect AI: uma aplicação
Next.js (App Router) que consome exclusivamente as APIs já existentes do
backend (Fases 0-4) para dar visibilidade operacional sobre prospects,
auditorias, Opportunity Scores e Sales Briefs — e para disparar as ações já
implementadas (nova pesquisa, rodar auditoria, calcular score, gerar
briefing).

Nenhuma regra de negócio foi duplicada no frontend: Website Quality,
Opportunity Score e Sales Brief continuam calculados exclusivamente pelo
backend (`app.domains.audit`, `app.domains.scoring`, `app.domains.briefing`).
O frontend só lê e exibe.

## Stack

| Camada | Escolha | Por quê |
|---|---|---|
| Framework | Next.js 16 (App Router, Turbopack) | Já estava planejado desde a Fase 0 (`docs/architecture.md`: "Frontend: Next.js (planejado)"). |
| Linguagem | TypeScript | Mesmo alinhamento de tipos que os response models Pydantic do backend (`frontend/src/lib/api/types.ts` espelha exatamente `backend/app/api/routes/*.py`). |
| Estilo | Tailwind CSS v4 | Já vem integrado ao template oficial do Next.js; base para o shadcn/ui. |
| Design system | shadcn/ui (preset `base-nova`, base `@base-ui/react`) | Pedido explicitamente pelo Prompt 08. Instalado via `npx shadcn@latest init` + `add` — só os componentes realmente usados (ver "Componentes shadcn/ui usados" abaixo). |
| Ícones | lucide-react | Dependência do próprio shadcn/ui, não uma escolha adicional. |
| Testes | Vitest + React Testing Library | Testa componentes de apresentação e funções puras; ver "Testes" abaixo para o que fica de fora e por quê. |

Nenhuma dependência de IA/agentes foi adicionada (sem CrewAI, AutoGen,
LangChain, Open Canvas, GPT Engineer) — o Dashboard é só uma interface HTTP
sobre APIs já existentes, nunca um agente.

## Arquitetura: Server Components + Server Actions

Toda leitura de dados (`lib/api/*.ts`) roda **exclusivamente no servidor
Next.js** — em Server Components (`page.tsx`) ou Server Actions
(`actions.ts`, diretiva `"use server"`), nunca em Client Components. Isso
tem uma consequência de segurança direta: o navegador nunca conversa
diretamente com o backend Python — só com o próprio Next.js — então a URL
do backend, quaisquer detalhes de rede, e principalmente qualquer API key
(`ANTHROPIC_API_KEY`, `GOOGLE_MAPS_API_KEY`) nunca aparecem na aba de rede
do navegador nem no bundle JavaScript enviado ao cliente. Verificado
manualmente: `grep` nos artefatos estáticos gerados (`.next/static`) não
encontra a URL do backend nem qualquer string relacionada à Anthropic (ver
seção "Validação real" no relatório da Fase 5).

O pacote `server-only` (dependência oficial mínima, mantida pelo time do
React) é importado no topo de cada módulo em `lib/api/` — ele lança um erro
em build se algum desses módulos for importado, por engano, a partir de um
Client Component.

Mutações (nova pesquisa, rodar auditoria, calcular score, gerar briefing)
usam **Server Actions** (`actions.ts` em cada rota) em vez de rotas de API
do Next.js — o mesmo motivo: a chamada ao backend Python acontece no
servidor, nunca no navegador. Cada botão de ação usa `useActionState`/
`useFormStatus` (React 19) para mostrar estado de carregamento e erro
inline, sem JavaScript customizado de fetch no cliente.

## Estrutura de rotas

```
/                          → redireciona para /dashboard
/dashboard                 → KPIs + oportunidades prioritárias + pesquisas recentes
/prospects                 → tabela paginada e filtrável de empresas
/prospects/[companyId]     → detalhe completo (identidade, descoberta, website,
                              website quality, opportunity score, breakdown,
                              evidências, sales brief)
/pesquisas                 → histórico de SearchRun (Fase 1)
/pesquisas/nova            → formulário para iniciar uma nova busca
/pesquisas/[runId]         → detalhe de uma execução
/configuracoes             → informações reais do ambiente (URL da API,
                              fases implementadas) — sem preferências de
                              usuário, já que não há autenticação
```

Cada rota de dados tem `loading.tsx` (skeleton — usa o Suspense boundary
nativo do App Router) e `error.tsx` (mensagem amigável + botão "Tentar
novamente", nunca um stack trace). `/prospects/[companyId]` também tem
`not-found.tsx` para uma `Company` inexistente.

## API do backend usada/criada

### Já existentes (Fases 1-4), reutilizadas sem alteração de comportamento

`POST/GET /api/audit/{id}`, `POST/GET /api/scoring/{id}`,
`POST/GET /api/sales-brief/{id}`, `POST /api/discovery/search`,
`GET /api/discovery/runs/{id}`.

### Novas nesta fase (leitura agregada, sem lógica de negócio nova)

O Dashboard precisava listar/agregar empresas de um jeito que nenhuma rota
anterior fazia (todas as Fases 1-4 seguem o padrão "uma empresa por vez").
Endpoints adicionados em `app/api/routes/companies.py`, apoiados por
`app/domains/companies/queries.py` (só consultas — nenhum cálculo de
Website Quality/Opportunity Score/Sales Brief acontece aqui):

- `GET /api/companies` — lista paginada (`limit`/`offset`) com filtros
  (`q`, `tier`, `min_score`/`max_score`, `site_state`, `category`, `region`,
  `audited`) e ordenação (`sort_by=created_at|opportunity_score`), já
  trazendo a auditoria/score mais recentes de cada empresa embutidos.
- `GET /api/companies/{company_id}` — agregação completa para a tela de
  detalhe: `Company` + fontes (`CompanySource`) + `Evidence` atual +
  `AuditSnapshot`/`WebsiteQuality` mais recentes + `OpportunityScore` mais
  recente + `SalesBrief` mais recente. Uma chamada só, em vez de 5.
- `GET /api/companies/meta/stats` — KPIs do Dashboard (total de empresas,
  quantas têm auditoria, quantas têm score ≥ 60, score médio), calculados
  inteiramente em SQL (`COUNT`/`AVG`/`SUM` condicional) — nunca aproximados
  buscando uma página parcial de resultados para o frontend somar.
- `GET /api/companies/meta/filters` — categorias/regiões que pelo menos uma
  `Company` já usa (nunca uma lista inventada de opções de filtro).
- `GET /api/discovery/runs` — lista paginada de `SearchRun` (só existia
  `GET .../runs/{id}` até a Fase 4).

Todos os quatro só fazem `SELECT`; nenhum grava dado, recalcula score ou
chama um provider externo.

## Componentes shadcn/ui usados

`button`, `card`, `badge`, `table`, `input`, `select` (Base UI — trocado por
`<select>` nativo especificamente no formulário de filtros, ver
"Decisões de UX"), `dialog`, `sheet` (menu mobile), `tabs` (instalado, não
usado ainda), `tooltip`, `skeleton`, `alert`, `separator` (instalado, não
usado ainda), `dropdown-menu` (instalado, não usado ainda), `label`,
`textarea` (instalado, não usado ainda), `scroll-area` (instalado, não
usado ainda). Componentes instalados mas não usados foram mantidos (custo
zero — só arquivos gerados, não dependências extras) em vez de removidos,
para ficarem disponíveis quando a Fase 6+ precisar sem reinstalar.

## Decisões de UX

- **Paleta**: neutro (cinza) com um único acento índigo (`oklch(0.47 0.2
  264)` no claro / `oklch(0.72 0.16 264)` no escuro) — nem o cinza puro
  padrão do shadcn, nem gradientes/glassmorphism. Cor de estado (tiers,
  site state, status de execução) é semântica e independente do acento
  (verde/âmbar/laranja/neutro), nunca reaproveita a cor de marca.
- **Cor nunca é o único indicador de estado**: todo badge de estado tem um
  ícone E um texto (`ConfidenceBadge`, `SiteStateBadge`,
  `RunStatusBadge`/`AuditStatusBadge`) — atende ao requisito de
  acessibilidade "não usar cor como único indicador".
- **`DataState` nunca é colapsado**: `not_detected`, `inconclusive`,
  `inaccessible`, `not_checked`, `stale` e `confirmed` têm rótulo, ícone e
  explicação (`SITE_STATE_DESCRIPTION`/`EVIDENCE_STATE_HEDGE`,
  `lib/format.ts`) próprios — nenhum vira "sem site" genérico.
- **Filtros são um `<form method="get">` nativo**, não um estado de cliente
  paralelo à URL. Cada filtro é um parâmetro de query string real — a URL
  de uma busca filtrada é compartilhável/atualizável no navegador sem
  JavaScript. `<select>` nativo (não o `Select` do shadcn/Base UI) foi uma
  escolha deliberada aqui: um `<select>` nativo participa de um formulário
  GET simples sem nenhum código extra de sincronização; o componente
  Base UI exigiria lógica adicional só para isso, sem ganho real de UX
  para uma lista de opções curta.
- **Mobile**: a tabela de prospects vira uma lista de cards com os mesmos
  dados (`ProspectsTable`, duas apresentações do mesmo array — nunca dados
  diferentes por breakpoint); a sidebar vira um `Sheet` (menu deslizante).

## Segurança

- Nenhuma API key é lida, armazenada ou exibida pelo frontend — confirmado
  por inspeção dos artefatos estáticos gerados (`.next/static`) sem
  nenhuma ocorrência de `ANTHROPIC`/`GOOGLE_MAPS_API_KEY`/da URL do
  backend.
- `API_BASE_URL` (não é um segredo — é só um endereço) é lido via
  `process.env` exclusivamente em código servidor; exibido de propósito em
  `/configuracoes` como informação de diagnóstico, nunca em nenhum lugar
  acessível ao JavaScript do navegador.
- Erros de API nunca chegam ao usuário como stack trace — `lib/api/
  client.ts` sempre converte para uma mensagem segura antes de propagar; o
  detalhe técnico completo vai para o log do servidor Next.js
  (`console.error`), nunca para a resposta HTML.
- Nenhuma autenticação foi implementada (fora de escopo da Fase 5,
  explicitamente) — todas as rotas continuam abertas, exatamente como o
  backend já era desde a Fase 0.

## Estados: loading, vazio, erro

- **Loading**: `loading.tsx` por rota (Suspense nativo do App Router) com
  skeletons dedicados (`KpiCardSkeletonList`, skeletons de tabela/detalhe).
  Botões de ação mostram um spinner + rótulo "…ando" via `useFormStatus`
  enquanto a Server Action está em voo.
- **Vazio**: `EmptyState` diferencia "nunca existiu nenhum prospect" de
  "nenhum resultado para estes filtros" (CTAs diferentes — "Nova pesquisa"
  vs. "Limpar filtros"), e da mesma forma para pesquisas/Sales Brief/
  auditoria ainda não executada.
- **Erro**: `error.tsx` por rota + `ErrorState`/`RouteError` compartilhados.
  Erros de ação (Server Actions) aparecem inline junto ao botão que os
  disparou (`ActionButton`), não como um redirecionamento de página cheia.

## Testes

**Frontend**: Vitest + React Testing Library, focado em componentes de
apresentação (badges, KPIs, seções de detalhe, tabela, filtros, formulário
de nova pesquisa, estados vazio/erro) e funções puras (`lib/format.ts`).

**O que fica fora dos testes automatizados de frontend, e por quê**: todo
módulo em `lib/api/*.ts` importa o pacote `server-only`, que lança um erro
imediatamente se importado fora do compilador do Next.js (verificado —
`server-only` distingue os ambientes via a condição de resolução
`react-server`, que só o bundler do Next define; Vitest resolve para o
`index.js` que sempre lança). Isso significa que:

- Nenhum teste de componente importa `lib/api/*.ts` diretamente — os
  componentes que dependem de dado já carregado recebem esse dado via
  `props` tipadas (`import type {...} from "@/lib/api/types"`, que não
  carrega nenhum código em tempo de execução).
- Componentes que importam uma Server Action (`ActionButton` via
  `SalesBriefSection`, `NewSearchForm`) têm a Server Action mockada via
  `vi.mock(...)` no teste — a ação real (`actions.ts`) nunca é executada em
  teste de componente.
- Os `page.tsx` (Server Components assíncronos que de fato chamam a API)
  não têm teste unitário — a cobertura deles vem da suíte de API do
  backend (`backend/tests/companies/`) mais a validação manual real
  descrita no relatório da Fase 5, mesma filosofia já usada pelo backend
  desde a Fase 0 (pytest + validação manual fora do pytest).

**Backend**: `backend/tests/companies/` (novo) cobre `list_companies`,
`get_company_detail`, `get_dashboard_stats`, `list_filter_options` e os
quatro endpoints HTTP novos; `backend/tests/discovery/test_api.py` ganhou
os testes de `GET /api/discovery/runs`. Nenhum teste de F0-F4 foi alterado.

## Performance

- **Sem polling**: nenhuma página atualiza sozinha. Cada navegação (ou
  clique em "Tentar novamente"/recarregar) busca dados frescos
  (`cache: "no-store"` em todo `fetch`) — não há WebSocket nem
  `setInterval`.
- **Paginação real**: `GET /api/companies` e `GET /api/discovery/runs` usam
  `LIMIT`/`OFFSET` de verdade no banco — a paginação do Dashboard nunca
  busca todos os registros para fatiar no frontend.
- **Uma chamada por tela de detalhe**: `GET /api/companies/{id}` agrega
  tudo que a tela de detalhe precisa (identidade, fontes, evidência,
  auditoria, score, briefing) numa única requisição, em vez de 5
  chamadas separadas.
- **KPIs calculados em SQL**: `GET /api/companies/meta/stats` nunca busca
  todas as empresas para calcular a média/contagens no Node — usa
  `COUNT`/`AVG`/`SUM` condicional do próprio banco.

## Limitações conhecidas

1. **"Soft 404" no detalhe de um prospect inexistente**: `notFound()` é
   chamado dentro de `/prospects/[companyId]`, que tem um `loading.tsx`
   (Suspense boundary) — por design do Next.js App Router, uma vez que o
   streaming da resposta já começou como `200`, o status HTTP não pode
   mais mudar para `404` (a página `not-found.tsx` ainda renderiza
   corretamente, com `<meta name="robots" content="noindex">`, mas o
   status HTTP fica `200`). Documentado pelo próprio Next.js
   (`node_modules/next/dist/docs/.../not-found.md`, seção sobre o
   trade-off de status code com Suspense). Corrigir exigiria mover a
   checagem para fora do Suspense boundary (`proxy`/middleware) — fora do
   escopo desta fase.
2. **Corrida rara em `list_companies`/`get_dashboard_stats`**: se duas
   auditorias da mesma empresa tiverem `created_at` idêntico até o
   microssegundo (praticamente impossível em uso real), a consulta de
   "auditoria mais recente por empresa" pode casar as duas e duplicar a
   linha na listagem — documentado também em
   `app/domains/companies/queries.py`.
3. **Nenhuma atualização em tempo real**: uma pesquisa/auditoria/score/
   briefing em andamento só aparece atualizado quando a página é recarregada
   ou uma Server Action de mesma tela revalida a rota
   (`revalidatePath`) — não há long-polling nem WebSocket.
4. **`/configuracoes` não tem nenhuma preferência configurável de verdade**
   — o sistema ainda não tem autenticação/multi-tenant (fora de escopo);
   a tela existe para não deixar o item de navegação pedido pela Fase 5
   vazio, e mostra só informação real e não-sensível do ambiente.
5. Reafirma-se toda limitação já documentada em `docs/development.md`
   (sem Docker/PostgreSQL/Redis reais nesta máquina, sem chamada real à
   API da Anthropic) — o Dashboard não contorna nenhuma delas, só as
   exibe honestamente (ex.: `/configuracoes` mostra a URL da API
   configurada; um Sales Brief sem chave real aparece como `status:
   "failed"`, nunca como sucesso fabricado).

## Como rodar

```bash
cd frontend
cp .env.example .env.local   # ajuste API_BASE_URL se o backend não estiver em localhost:8000
npm install
npm run dev      # http://localhost:3000, backend precisa estar no ar em paralelo
```

```bash
npm run build && npm run start   # build de produção
npm run lint                     # ESLint
npm run test                     # Vitest (roda uma vez; sem watch)
```
