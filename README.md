# Prospect AI

> **Fase 7 — CRM + Outreach.** Este README descreve o estado real do
> projeto nesta fase. Discovery, Identity Resolution, Digital Audit,
> Opportunity Score, Sales Brief, o Dashboard, o Prototype Builder e agora
> Autenticação + CRM (pipeline, contatos, timeline) + Assisted Outreach
> estão implementados; geração de código/publicação/envio automatizado de
> outreach ainda não. Ver `docs/crm.md`.

## O que é

Prospect AI é uma plataforma interna para uma agência de desenvolvimento
web descobrir e qualificar empresas locais como potenciais clientes de
sites, landing pages, sistemas de agendamento e aplicações web. O sistema
analisa a presença digital pública de uma empresa (site, redes sociais,
contatos comerciais publicados) e estima uma oportunidade comercial —
trabalhando exclusivamente com dados públicos/comerciais e fontes
autorizadas.

## Documentos de arquitetura

A decisão de arquitetura completa (v0.2, revisada e aprovada antes desta
implementação) descreve o pipeline completo, o modelo de dados conceitual,
os agentes futuros e o roadmap de 8 fases. Este repositório implementa,
até aqui, as **Fases 0, 1, 2, 3, 4, 5 e 6** desse roadmap.

- `docs/architecture.md` — estado real da arquitetura após a Fase 6.
- `docs/data-model.md` — schema de banco implementado, com as decisões e
  desvios documentados.
- `docs/discovery.md` — o domínio de Discovery em detalhe.
- `docs/identity-resolution.md` — o domínio de Identity Resolution em
  detalhe.
- `docs/digital-audit.md` — o domínio de Digital Audit em detalhe: fluxo,
  estados, SSRF, Evidence Layer, metodologia do Website Quality Score,
  limitações, testes.
- `docs/opportunity-scoring.md` — a fórmula do Opportunity Score:
  dimensões, pesos, classificação, confiança, limitações.
- `docs/sales-brief.md` — o Sales Brief: arquitetura, provider de IA,
  grounding, defesa contra prompt injection, tratamento de falhas.
- `docs/dashboard.md` — o Dashboard (Next.js): arquitetura, rotas, APIs
  consumidas/criadas, decisões de UX, segurança, testes, limitações.
- `docs/prototype-builder.md` — o Prototype Builder: modelo de dados,
  catálogo de componentes, segurança, arquitetura do editor, limitações
  (histórico: nas Fases 0-6 o projeto não tinha autenticação — resolvido na
  Fase 7, ver abaixo).
- `docs/crm.md` — Autenticação (JWT próprio), ownership/autorização, CRM
  (Opportunity/Pipeline/Contacts/Activities), Assisted Outreach + IA,
  segurança, variáveis de ambiente novas, limitações.
- `docs/development.md` — como rodar, testar e migrar backend e frontend.

## Stack

| Camada | Tecnologia |
|---|---|
| Backend | Python + FastAPI |
| Banco | PostgreSQL 16 (via Docker) |
| ORM / migrations | SQLAlchemy 2.0 + Alembic |
| Fila | Redis + RQ (com fallback síncrono documentado — ver `docs/discovery.md`) |
| Cliente HTTP externo | httpx, com timeout e retry limitado |
| Fonte de descoberta | Google Places API (New) |
| Similaridade de texto | RapidFuzz (matching de identidade) |
| Extração de HTML / SSRF | `html.parser`, `ipaddress`, `socket` (biblioteca padrão) |
| Opportunity Score | Determinístico, sem IA (`app.domains.scoring`) |
| Sales Brief | Claude API (Anthropic Messages API via `httpx` puro — sem SDK novo) |
| Logging | structlog (estruturado, com correlação por requisição) |
| Frontend | Next.js 16 (App Router) + TypeScript + Tailwind v4 + shadcn/ui (ver `docs/dashboard.md`) |
| Prototype Builder | Determinístico, sem IA — `useReducer` nativo, sem lib de estado nova (ver `docs/prototype-builder.md`) |

## Estrutura de diretórios

```
backend/
  app/
    core/                 # configuração, logging, erros, middleware
    api/routes/           # health, discovery, identity, audit, scoring, sales_brief, companies, prototypes
    db/                   # base declarativa, sessão, registro de modelos
    domains/
      discovery/          # DiscoveryQuery, normalização, service, jobs, cache
        providers/        # contrato DiscoveryProvider + GooglePlacesProvider
      identity/           # matching, profile, service (Identity Resolution)
      audit/               # ssrf, http_client, html_signals, scoring, service, jobs
      scoring/             # Opportunity Score: ScoringContext, fórmula, service
      briefing/            # Sales Brief: prompt, schemas, providers/, service, jobs
      companies/           # models + queries.py (agregação de leitura do Dashboard)
      prototypes/          # models, schemas (validação da árvore), service
      evidence/
    jobs/                 # abstrações de job e conexão com a fila
  migrations/             # Alembic (6 migrations)
  tests/
    discovery/            # testes do domínio discovery (sem chamadas reais)
    identity/             # testes do domínio identity (sem chamadas reais)
    audit/                # testes do domínio audit (sem chamadas reais)
    scoring/              # testes do domínio scoring (puros + integração, sem IA)
    briefing/             # testes do domínio briefing (provider sempre mockado/fake)
    companies/             # testes das consultas/API agregada do Dashboard
    prototypes/             # validação da árvore, CRUD e API do Prototype Builder
frontend/          # Dashboard + Prototype Builder (Next.js) — ver docs/dashboard.md,
                   # docs/prototype-builder.md e frontend/README.md
  src/app/           # rotas (App Router)
  src/components/    # ui/ (shadcn), badges/, layout/, dashboard/, prospects/,
                     # prototype-builder/, ...
  src/lib/           # api/ (cliente HTTP server-only), prototype/ (catálogo), format.ts
infra/           # notas de infraestrutura
docs/            # documentação de arquitetura, dados, discovery, identity, audit,
                 # scoring, sales brief, dashboard e prototype builder
docker-compose.yml
```

## Como instalar e rodar

### Com Docker (recomendado)

```bash
cp backend/.env.example backend/.env
# edite backend/.env e informe GOOGLE_MAPS_API_KEY se for usar Discovery de verdade
docker compose up --build
```

A API sobe em `http://localhost:8000`. As migrations são aplicadas
automaticamente na inicialização do container `backend`.

> **Atenção:** este `docker compose up` não foi executado durante esta
> implementação — a máquina usada não tinha Docker instalado. Ver
> "Limitações conhecidas" abaixo antes de assumir que funciona sem revisão.

### Sem Docker

Requer PostgreSQL e Redis próprios, rodando nos endereços configurados em
`backend/.env`.

```bash
cd backend
cp .env.example .env
python -m venv .venv
source .venv/Scripts/activate   # Windows Git Bash; ajuste para seu shell
pip install -r requirements-dev.txt

alembic upgrade head
uvicorn app.main:app --reload
```

### Rodando os testes

```bash
cd backend
pytest -v
```

Os testes rodam contra SQLite (não exigem Postgres/Redis reais) e nenhum
faz uma chamada de rede real — ver `docs/development.md`,
`docs/discovery.md` e `docs/digital-audit.md` para o porquê e as
implicações disso.

### Rodando o Dashboard (frontend)

Requer Node.js 20+ e o backend já no ar.

```bash
cd frontend
cp .env.example .env.local
npm install
npm run dev
```

Abre em `http://localhost:3000`. Ver `docs/dashboard.md` e
`frontend/README.md` para detalhes, e `npm run test` (Vitest) para a
suíte de testes do frontend.

## Endpoints

```
GET  /health                    → {"status": "ok", "service": "Prospect AI", "environment": "..."}
GET  /health/dependencies       → {"status": "ok"|"degraded", "checks": {"database": "...", "redis": "..."}}
POST /api/discovery/search      → cria e executa uma busca de descoberta (ver docs/discovery.md)
GET  /api/discovery/runs/{id}   → consulta o estado de uma execução
POST /api/identity/resolve      → decide (sem persistir) se um candidato bate com uma empresa existente
POST /api/audit/{company_id}    → cria e executa uma auditoria digital (ver docs/digital-audit.md)
GET  /api/audit/{company_id}    → consulta a auditoria mais recente da empresa
POST /api/scoring/{company_id}  → calcula/recalcula o Opportunity Score (ver docs/opportunity-scoring.md)
GET  /api/scoring/{company_id}  → consulta o Opportunity Score mais recente
POST /api/sales-brief/{company_id} → gera um Sales Brief via IA (ver docs/sales-brief.md)
GET  /api/sales-brief/{company_id} → consulta o Sales Brief mais recente
GET  /api/discovery/runs        → lista pesquisas (paginado, filtro por status) — Fase 5
GET  /api/companies             → lista/filtra/pagina empresas com auditoria e score embutidos — Fase 5
GET  /api/companies/{id}        → agregação completa para a tela de detalhe do Dashboard — Fase 5
GET  /api/companies/meta/stats  → KPIs do Dashboard, calculados em SQL — Fase 5
GET  /api/companies/meta/filters → categorias/regiões em uso, para os filtros do Dashboard — Fase 5
GET  /api/prototypes/meta/component-types → catálogo de tipos de componente aceitos — Fase 6
POST /api/prototypes            → cria um protótipo (nome + descrição) — Fase 6
GET  /api/prototypes            → lista protótipos (paginado) — Fase 6
GET  /api/prototypes/{id}       → detalhe completo (árvore de componentes) — Fase 6
PUT  /api/prototypes/{id}       → atualiza nome/descrição/árvore/settings — Fase 6
DELETE /api/prototypes/{id}     → exclui um protótipo — Fase 6
```

Exemplo — Discovery:

```bash
curl -X POST http://localhost:8000/api/discovery/search \
  -H "Content-Type: application/json" \
  -d '{"region": "Interlagos", "city": "São Paulo", "category": "restaurantes", "max_results": 5}'
```

Exemplo — Identity Resolution:

```bash
curl -X POST http://localhost:8000/api/identity/resolve \
  -H "Content-Type: application/json" \
  -d '{"source": "openstreetmap", "external_id": "node/1", "name": "REST. SAO JOAO", "phone": "+5511987654321"}'
```

Exemplo — Digital Audit (a empresa precisa já ter uma `Evidence` de
`website`, produzida pelo Discovery ou inserida manualmente):

```bash
curl -X POST http://localhost:8000/api/audit/<company_id>
```

Exemplo — Opportunity Score (precisa de uma auditoria já executada) e
Sales Brief (precisa de um Opportunity Score já calculado; sem
`ANTHROPIC_API_KEY` configurada, responde `status: "failed"` de forma
controlada):

```bash
curl -X POST http://localhost:8000/api/scoring/<company_id>
curl -X POST http://localhost:8000/api/sales-brief/<company_id>
```

## O que está implementado

**Fase 0 — Foundation**

- Backend FastAPI com health check e tratamento de erro consistente.
- Schema de banco completo para as entidades estruturais da arquitetura
  v0.2: `Company` (sem depender de identificador externo), `CompanySource`
  (múltiplas fontes por empresa), `Evidence` (proveniência, append-only),
  `AuditSnapshot`, `WebsiteQuality`, `OpportunityScore`, `Region`,
  `Category`.
- Estados não-binários de dado (`confirmed`, `not_detected`,
  `inconclusive`, `inaccessible`, `not_checked`, `stale`) como enum
  reutilizável — nenhuma checagem de presença digital pode colapsar
  "não verificado" em "não existe".
- Configuração centralizada via variáveis de ambiente, sem nenhum segredo
  real versionado. Logging estruturado com `request_id` por requisição.
- Abstração de job (`Job`, `JobContext`) e conexão com a fila Redis/RQ.

**Fase 1 — Discovery**

- `DiscoveryQuery`: validação de entrada com limites internos rígidos.
- `GooglePlacesProvider`: Text Search e Nearby Search da Google Places API
  **New**, com timeout, retry limitado, paginação e FieldMask mínimo
  justificado campo a campo (ver `docs/discovery.md`).
- `DiscoveryService`: orquestra `SearchRun -> provider -> normalização ->
  persistência` — só descobre e registra candidatos.
- Cache best-effort, `ProviderUsageRecord` para custo por chamada, API HTTP.

**Fase 2 — Identity Resolution + Deduplicação**

- `IdentityResolutionService`: compara um candidato inédito contra
  empresas já conhecidas por telefone, site oficial, nome (RapidFuzz),
  endereço, região e proximidade geográfica (Haversine) antes de decidir
  entre reaproveitar uma `Company` existente ou criar uma nova. Nenhum
  sinal isolado decide um merge automático.
- `DedupCandidate`: audita toda decisão não trivial; ambíguas ficam
  `pending_review` para revisão humana futura, nunca fundidas
  automaticamente.
- `IdentityResolutionService.merge_companies`: funde duas `Company` já
  existentes preservando todo o histórico — testado na camada de serviço,
  ainda sem endpoint HTTP.

**Fase 3 — Digital Audit + Website Quality Score**

- `select_website_candidate`: lê o `Evidence` de `website` já existente da
  empresa (produzido por Discovery/Identity Resolution) — nunca descobre
  um site novo. Nunca trata Instagram/Facebook/TikTok/WhatsApp/Linktree/
  marketplaces/mapas como website oficial; candidatos conflitantes entre
  fontes viram `inconclusive`, nunca uma escolha arbitrária.
- **Proteção contra SSRF** (`app/domains/audit/ssrf.py`): valida esquema,
  ausência de credenciais embutidas e o(s) endereço(s) IP resolvido(s) de
  cada URL — bloqueando loopback, redes privadas (RFC1918), link-local
  (inclui o endpoint de metadata de nuvem), multicast, reservado, CGNAT e
  faixas de teste/benchmarking. Revalidado a cada redirecionamento, não só
  na URL inicial.
- `fetch_safely`: busca HTTP com timeout obrigatório, limite de
  redirecionamentos, limite de tamanho de resposta (truncamento, nunca
  rejeição automática), retry limitado só para erros transitórios, e
  User-Agent identificável. 4xx/5xx são resultados válidos, não exceções.
- `extract_html_signals`: extração determinística de sinais técnicos
  (title, meta description, headings, links, formulário, contato,
  redes sociais) via `html.parser` da biblioteca padrão — nunca executa
  JavaScript; conteúdo de `<script>`/`<style>` nunca vira sinal nem é
  tratado como instrução.
- **Website Quality Score** (`app/domains/audit/scoring.py`): cinco
  dimensões (segurança, SEO, conteúdo, UX, técnico) combinadas por média
  ponderada documentada — função pura e reproduzível, sem IA. Separado do
  Opportunity Score (Fase 4): mede qualidade técnica, nunca "chance de
  venda". `score=None` (nunca `0`) quando o site não foi confirmado como
  acessível.
- `AuditSnapshot` histórico (nunca sobrescrito) com `status` (processo) e
  `site_state` (o que foi encontrado) como conceitos distintos — um site
  inacessível ou bloqueado por SSRF é `status=completed`, nunca `failed`.
- Evidence append-only reaproveitando o mesmo padrão do Discovery
  (generalizado em `evidence.queries.upsert_evidence`).
- API HTTP (`POST`/`GET /api/audit/{company_id}`), validada com uma
  chamada de rede real contra `https://example.com`.

**Fase 4 — Opportunity Score + Sales Brief**

- **Opportunity Score determinístico** (`app.domains.scoring.scoring`):
  combina 6 dimensões (Website Gap, Website Quality Gap, Digital Presence
  Gap, Business Visibility, Segment Fit, Contactability) em um score 0-100
  por média ponderada, com pesos documentados e configuráveis. Nenhuma
  dimensão sem evidência suficiente vira 0 ou 100 por suposição — é
  excluída, e os pesos restantes são renormalizados. Separado do Website
  Quality Score (Fase 3): nunca a mesma coisa, nunca uma cópia/transformação
  trivial. `rating`/`review_count` entram só como sinal de visibilidade
  pública, nunca como proxy de faturamento — com saturação explícita para
  nunca deixar um volume alto de avaliações dominar o score. Ver
  `docs/opportunity-scoring.md`.
- `OpportunityScore` ganhou `confidence` (reflete quantidade/qualidade de
  sinal disponível, separado do valor do score), `scoring_version` e
  classificação em 5 faixas (`high`/`medium_high`/`medium`/`low`/
  `very_low`, ampliado do placeholder de 3 faixas da Fase 0). `breakdown`
  grava, por dimensão, valor bruto, peso, contribuição, razão textual e
  referências de evidência — toda decisão é auditável.
- **Sales Brief** (`app.domains.briefing`): único componente de todo o
  sistema que chama um provider de IA (Anthropic, via `httpx` puro — sem
  adicionar o SDK `anthropic` como dependência). Grounding estrito: usa
  somente `Company`/`Evidence`/`AuditSnapshot`/`WebsiteQuality`/
  `OpportunityScore` já existentes, nunca pesquisa nada novo, nunca inventa
  faturamento/funcionários/orçamento/tecnologias/clientes/intenção de
  compra. Toda a saída é validada contra um schema estrutural
  (`SalesBriefContent`) antes de ser aceita — uma resposta inválida vira
  `status=failed`, nunca um briefing malformado persistido como sucesso.
- **Defesa contra prompt injection**: todo dado de `Evidence`/
  `WebsiteQuality` é interpolado dentro de um bloco de dados delimitado,
  nunca dentro do `system prompt` (que é uma constante fixa); ocorrências
  literais do delimitador dentro de uma evidência são neutralizadas antes
  da interpolação, para que um valor malicioso não consiga "escapar" do
  bloco de dados. Testado estruturalmente e com um cenário de injeção
  fim-a-fim (`tests/briefing/`).
- **Degradação graciosa**: sem `ANTHROPIC_API_KEY` configurada, o Sales
  Brief responde de forma controlada (`status=failed`,
  `error_code=ProviderUnavailableError`) — nunca um crash, nunca um
  briefing inventado. O Opportunity Score é inteiramente independente e
  continua funcionando normalmente.
- API HTTP (`POST`/`GET /api/scoring/{company_id}` e
  `POST`/`GET /api/sales-brief/{company_id}`), validada de ponta a ponta
  com um servidor real e uma auditoria real contra `https://example.com` —
  a chamada de IA em si sempre com um provider mockado, nunca uma chamada
  real à Anthropic. Ver `docs/sales-brief.md`.

**Fase 5 — Dashboard**

- **Interface Next.js (App Router)** consumindo só leitura + as ações HTTP
  já existentes — nenhuma regra de negócio nova, nenhum cálculo de score/
  qualidade duplicado no frontend. Todo acesso ao backend acontece em
  Server Components/Server Actions, nunca no navegador — o browser só
  conversa com o próprio Next.js.
- **Visão geral** com KPIs reais (prospects, alta oportunidade, auditados,
  score médio — todos calculados em SQL, nunca aproximados), oportunidades
  prioritárias e pesquisas recentes.
- **Prospects**: tabela paginada e filtrável (classificação, faixa de
  score, presença de website, segmento, região, status de auditoria,
  busca por nome) — filtros são uma URL real (`<form method="get">`),
  compartilhável/atualizável no navegador.
- **Detalhe do prospect**: identidade, descoberta (fontes), website,
  Website Quality Score, Opportunity Score com breakdown explicável por
  dimensão (valor, peso, contribuição, razão, evidência), evidências com
  proveniência completa, e Sales Brief (com botão para gerar, chamando a
  API real da Fase 4 — nunca uma resposta fabricada no frontend).
- **Pesquisas**: histórico de `SearchRun` e formulário para iniciar uma
  nova busca — nunca lista um provider de Discovery fictício.
- Estados de loading (skeletons), vazio (com CTA apropriado) e erro
  (mensagem amigável, nunca stack trace) tratados explicitamente em toda
  tela. Ver `docs/dashboard.md`.
- 4 endpoints novos de leitura agregada (`GET /api/companies`,
  `GET /api/companies/{id}`, `GET /api/companies/meta/stats`,
  `GET /api/companies/meta/filters`) + `GET /api/discovery/runs` (lista) —
  todos só consultam, nenhum recalcula nada.

**Migrations e testes**: 5 migrations Alembic aplicadas e testadas
(schema inicial; execução de busca; resolução de identidade; auditoria
digital; Opportunity Score e Sales Brief — a Fase 5 não alterou o schema).
Backend: 339 testes (304 das Fases 0-4 + 35 novos de
`app.domains.companies`/`GET .../runs`). Frontend: 71 testes (Vitest +
React Testing Library).

**Fase 6 — Prototype Builder**

- **Auditoria prévia revelou um achado crítico**: o Prospect AI não tem
  autenticação em nenhuma fase (busca direta confirmou zero JWT/OAuth/
  login/sessão em todo o backend) — o Prompt 09 presumia isso já pronto.
  `Prototype.owner_id` existe como coluna reservada mas não é usado para
  isolar nada nesta fase, mesmo precedente já aceito para a fusão de
  `Company` desde a Fase 2. Ver `docs/prototype-builder.md`.
- **Catálogo de 12 componentes iniciais** (Container, Section, Row,
  Column, Text, Heading, Button, Image, Input, Textarea, Card, Divider) —
  pequeno de propósito; adicionar um tipo novo não exige mudar a estrutura
  de `Prototype`.
- **Segurança**: catálogo de tipos fechado (backend rejeita qualquer
  `type` fora da lista, nunca confia no frontend), `props`/`styles`
  restritos a primitivos curtos (nenhum objeto/lista, tamanho limitado),
  limites de tamanho/profundidade da árvore com detecção de ciclo. No
  frontend, nenhum `dangerouslySetInnerHTML` em lugar nenhum — texto do
  usuário é sempre filho de texto comum do React; `<img src>` rejeita
  esquemas perigosos (`javascript:`, `data:text/html`).
- **Canvas e Preview usam exatamente o mesmo renderer** — nunca uma
  segunda implementação da interface.
- **Estado do Builder**: um único `useReducer`, sem biblioteca de estado
  nova — undo/redo incluído (pilha de snapshots, com agrupamento de
  edições de texto num único passo de histórico).
- Árvore de componentes salva como lista plana (`parent_id`/`order`), não
  aninhada — adicionar/mover/remover um nó nunca exige reescrever a
  árvore inteira.
- Sem drag-and-drop nesta fase (permitido pelo próprio Prompt 09:
  "priorize estabilidade") — adicionar/selecionar/mover/remover funcionam
  via clique e botões.
- 6 endpoints novos (`GET /api/prototypes/meta/component-types`,
  `POST`/`GET /api/prototypes`, `GET`/`PUT`/`DELETE /api/prototypes/{id}`)
  — nenhuma IA, nenhuma geração de código.

**Migrations e testes**: 6 migrations Alembic (a Fase 6 acrescenta
`prototypes`). **Backend: 379 testes ao todo** (339 das Fases 0-5 + 40
novos em `tests/prototypes/` — validação da árvore, CRUD, API); 378 passam
por padrão sem qualquer chamada de rede real, e 1 é o teste de integração
real e opcional da Fase 1, ignorado por padrão. **Frontend: 131 testes**
(71 da Fase 5 + 60 novos do Prototype Builder — reducer/undo-redo,
segurança do renderer, canvas, painel de propriedades, paleta, diálogo de
criação, integração). Ver `docs/prototype-builder.md`, seção "Testes".

## O que NÃO está implementado ainda

- Fusão de duas `Company` exposta por HTTP (existe e é testada só na
  camada de serviço — falta autenticação/autorização no sistema).
- Consumo da fila de revisão humana do Identity Resolution — existe e é
  populada; falta uma interface dedicada.
- Qualquer agente de IA multi-etapa ou framework de agentes (CrewAI,
  AutoGen, LangChain, LangGraph) — o Sales Brief é uma única chamada
  request/response a um provider de texto, não um agente.
- Uma chamada real à API da Anthropic (sem `ANTHROPIC_API_KEY` disponível
  neste ambiente de desenvolvimento).
- Outros providers de Discovery (OpenStreetMap fica documentado como
  extensão futura).
- PostGIS (distância geográfica calculada em Python, tanto na Fase 2
  quanto na Fase 3).
- Proteção completa contra DNS rebinding via IP pinning no Digital Audit
  — a validação por resolução prévia existe; fixar a conexão TCP ao IP
  validado, não (ver `docs/digital-audit.md`).
- Crawling: o Digital Audit analisa só a página inicial do candidato.
- Autenticação/autorização, multi-tenant, atualização em tempo real no
  Dashboard nem no Prototype Builder (sem WebSocket/polling, sem
  colaboração — ver `docs/dashboard.md` e `docs/prototype-builder.md`).
- No Prototype Builder: drag-and-drop, geração de código, publicação/
  deploy, domínio personalizado, marketplace de componentes, sistema de
  plugins, histórico ilimitado (ver `docs/prototype-builder.md`, "O que
  NÃO foi implementado").
- CRM, outreach, billing.

## Limitações conhecidas

A máquina usada para esta implementação não tem Docker, WSL, PostgreSQL
nem Redis instalados — apenas Python e Node. Por decisão explícita, isso
teve consequências práticas:

1. Os testes automatizados validam o schema e a lógica de modelo contra
   **SQLite**, aplicando as migrations reais do Alembic — não contra
   PostgreSQL.
2. `docker compose up` **não foi executado** nesta implementação.
3. `POST /api/discovery/search` e `POST /api/audit/{company_id}` sempre
   rodam em modo síncrono de fallback nesta máquina (sem Redis para
   enfileirar de verdade) — o caminho enfileirado (RQ) está implementado e
   testado quanto ao *fallback*, mas nunca foi exercitado ponta a ponta
   com um worker real.
4. Nenhuma chamada real à Google Places API foi feita — não há chave de
   API disponível neste ambiente. O Digital Audit, por outro lado, **foi**
   validado com uma chamada de rede real contra `https://example.com`
   (ver `docs/digital-audit.md`).
5. Os limiares de similaridade do Identity Resolution, os pesos do
   Website Quality Score e os pesos/tabela de segmento do Opportunity
   Score foram calibrados manualmente contra os exemplos dos respectivos
   prompts de implementação — não contra dados reais.
6. **Nenhuma chamada real à API da Anthropic foi feita** — não há
   `ANTHROPIC_API_KEY` disponível neste ambiente. O Sales Brief foi
   validado de ponta a ponta (servidor real, banco real, Opportunity Score
   real) com um provider de IA mockado — nunca uma chamada real. O caminho
   de degradação graciosa sem chave configurada é, ele mesmo, o estado
   real desta máquina, e também foi validado de verdade (ver
   `docs/sales-brief.md`).
7. **O Dashboard (Fase 5) foi validado com um build de produção real do
   Next.js** (`npm run build && npm run start`) contra um backend real
   nesta máquina — listagem, filtros, detalhe completo, nova pesquisa,
   Sales Brief (mockado) e estados de erro/vazio, todos exercitados
   manualmente. Um "soft 404" documentado (status HTTP 200 em vez de 404
   ao abrir um prospect inexistente) é uma limitação conhecida do Next.js
   App Router quando a rota tem um `loading.tsx` — a UI correta ainda
   assim é exibida (ver `docs/dashboard.md`, seção "Limitações
   conhecidas").
8. **O Prototype Builder (Fase 6) não tem autenticação** — mesma limitação
   estrutural do restante do sistema (achado de auditoria: zero
   JWT/OAuth/login em todo o backend). `Prototype.owner_id` existe mas
   não isola nada. Validado com o mesmo servidor de produção Next.js +
   backend real: criação, edição da árvore, validação de segurança
   (tipo fora do catálogo e propriedade aninhada corretamente rejeitados,
   sem corromper o protótipo já salvo), exclusão, e ausência de segredos
   no bundle — mesmo "soft 404" do item 7 acima também se aplica aqui.
   Ver `docs/prototype-builder.md`.

Nenhuma decisão de arquitetura foi alterada por causa dessas limitações —
são lacunas de validação de ambiente, documentadas para serem fechadas
assim que houver Docker/Redis/uma chave de API/dados reais disponíveis,
não mudanças de design. Ver `docs/development.md`, `docs/discovery.md`,
`docs/identity-resolution.md`, `docs/digital-audit.md`,
`docs/opportunity-scoring.md`, `docs/sales-brief.md`, `docs/dashboard.md`
e `docs/prototype-builder.md` para o detalhe de cada uma.

## Próxima fase

**Fase 7**, conforme o roadmap da arquitetura v0.2. Não inicia
automaticamente: aguarda aprovação explícita.
