# Prospect AI

> **Fase 3 — Digital Audit + Website Quality Score.** Este README descreve
> o estado real do projeto nesta fase. Discovery, Identity Resolution e
> Digital Audit estão implementados; pontuação de oportunidade e geração
> de briefing ainda não.

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
até aqui, as **Fases 0, 1, 2 e 3** desse roadmap.

- `docs/architecture.md` — estado real da arquitetura após a Fase 3.
- `docs/data-model.md` — schema de banco implementado, com as decisões e
  desvios documentados.
- `docs/discovery.md` — o domínio de Discovery em detalhe.
- `docs/identity-resolution.md` — o domínio de Identity Resolution em
  detalhe.
- `docs/digital-audit.md` — o domínio de Digital Audit em detalhe: fluxo,
  estados, SSRF, Evidence Layer, metodologia do Website Quality Score,
  limitações, testes.
- `docs/development.md` — como rodar, testar e migrar o backend.

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
| Logging | structlog (estruturado, com correlação por requisição) |
| Frontend | Ainda não iniciado (ver `frontend/README.md`) |

## Estrutura de diretórios

```
backend/
  app/
    core/                 # configuração, logging, erros, middleware
    api/routes/           # health, discovery, identity, audit
    db/                   # base declarativa, sessão, registro de modelos
    domains/
      discovery/          # DiscoveryQuery, normalização, service, jobs, cache
        providers/        # contrato DiscoveryProvider + GooglePlacesProvider
      identity/           # matching, profile, service (Identity Resolution)
      audit/               # ssrf, http_client, html_signals, scoring, service, jobs
      companies/, evidence/, scoring/, briefing/
    jobs/                 # abstrações de job e conexão com a fila
  migrations/             # Alembic (4 migrations)
  tests/
    discovery/            # testes do domínio discovery (sem chamadas reais)
    identity/             # testes do domínio identity (sem chamadas reais)
    audit/                # testes do domínio audit (sem chamadas reais)
frontend/        # placeholder — dashboard é Fase 5
infra/           # notas de infraestrutura
docs/            # documentação de arquitetura, dados, discovery, identity, audit e desenvolvimento
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

## Endpoints

```
GET  /health                    → {"status": "ok", "service": "Prospect AI", "environment": "..."}
GET  /health/dependencies       → {"status": "ok"|"degraded", "checks": {"database": "...", "redis": "..."}}
POST /api/discovery/search      → cria e executa uma busca de descoberta (ver docs/discovery.md)
GET  /api/discovery/runs/{id}   → consulta o estado de uma execução
POST /api/identity/resolve      → decide (sem persistir) se um candidato bate com uma empresa existente
POST /api/audit/{company_id}    → cria e executa uma auditoria digital (ver docs/digital-audit.md)
GET  /api/audit/{company_id}    → consulta a auditoria mais recente da empresa
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

**Migrations e testes**: 4 migrations Alembic aplicadas e testadas
(schema inicial; execução de busca; resolução de identidade; auditoria
digital). **242 testes ao todo** (138 das Fases 0-2 + 102 do domínio
`audit`, incluindo os cenários de SSRF, redirects, extração de HTML e
determinismo do score, + 2 novas checagens de migration); 241 passam por
padrão sem qualquer chamada de rede, e 1 é o teste de integração real e
opcional da Fase 1, ignorado por padrão.

## O que NÃO está implementado ainda

- Fusão de duas `Company` exposta por HTTP (existe e é testada só na
  camada de serviço — falta autenticação/autorização no sistema).
- Consumo da fila de revisão humana do Identity Resolution — existe e é
  populada; falta uma interface (Fase 5).
- Qualquer cálculo de Opportunity Score ou geração de Sales Brief.
- Qualquer agente de IA (nenhuma chamada à API da Anthropic — Discovery,
  Identity Resolution e Digital Audit são inteiramente determinísticos).
- Outros providers de Discovery (OpenStreetMap fica documentado como
  extensão futura).
- PostGIS (distância geográfica calculada em Python, tanto na Fase 2
  quanto na Fase 3).
- Proteção completa contra DNS rebinding via IP pinning no Digital Audit
  — a validação por resolução prévia existe; fixar a conexão TCP ao IP
  validado, não (ver `docs/digital-audit.md`).
- Crawling: o Digital Audit analisa só a página inicial do candidato.
- Prototype Builder e CRM.
- Dashboard/frontend.

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
5. Os limiares de similaridade do Identity Resolution, e os pesos do
   Website Quality Score, foram calibrados manualmente contra os exemplos
   dos respectivos prompts de implementação — não contra dados reais.

Nenhuma decisão de arquitetura foi alterada por causa dessas limitações —
são lacunas de validação de ambiente, documentadas para serem fechadas
assim que houver Docker/Redis/uma chave de API/dados reais disponíveis,
não mudanças de design. Ver `docs/development.md`, `docs/discovery.md`,
`docs/identity-resolution.md` e `docs/digital-audit.md` para o detalhe de
cada uma.

## Próxima fase

**Fase 4 — Opportunity Score + Sales Brief**, conforme o roadmap da
arquitetura v0.2. Não inicia automaticamente: aguarda aprovação explícita.
