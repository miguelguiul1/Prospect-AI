# Prospect AI

> **Fase 1 — Discovery.** Este README descreve o estado real do projeto
> nesta fase. Discovery (descoberta de empresas via Google Places) está
> implementado; Identity Resolution, Digital Audit, pontuação de
> oportunidade e geração de briefing ainda não.

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
até aqui, as **Fases 0 e 1** desse roadmap.

- `docs/architecture.md` — estado real da arquitetura após a Fase 1.
- `docs/data-model.md` — schema de banco implementado, com as decisões e
  desvios documentados.
- `docs/discovery.md` — o domínio de Discovery em detalhe: fluxo,
  provider, FieldMask, erros, custos, limites, testes.
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
| Logging | structlog (estruturado, com correlação por requisição) |
| Frontend | Ainda não iniciado (ver `frontend/README.md`) |

## Estrutura de diretórios

```
backend/
  app/
    core/                 # configuração, logging, erros, middleware
    api/routes/           # health, discovery
    db/                   # base declarativa, sessão, registro de modelos
    domains/
      discovery/          # DiscoveryQuery, normalização, service, jobs, cache
        providers/        # contrato DiscoveryProvider + GooglePlacesProvider
      companies/, identity/, evidence/, audit/, scoring/, briefing/
    jobs/                 # abstrações de job e conexão com a fila
  migrations/             # Alembic (2 migrations)
  tests/
    discovery/            # testes do domínio discovery (sem chamadas reais)
frontend/        # placeholder — dashboard é Fase 5
infra/           # notas de infraestrutura
docs/            # documentação de arquitetura, dados, discovery e desenvolvimento
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
chama a API do Google de verdade — ver `docs/development.md` e
`docs/discovery.md` para o porquê e as implicações disso.

## Endpoints

```
GET  /health                    → {"status": "ok", "service": "Prospect AI", "environment": "..."}
GET  /health/dependencies       → {"status": "ok"|"degraded", "checks": {"database": "...", "redis": "..."}}
POST /api/discovery/search      → cria e executa uma busca de descoberta (ver docs/discovery.md)
GET  /api/discovery/runs/{id}   → consulta o estado de uma execução
```

Exemplo:

```bash
curl -X POST http://localhost:8000/api/discovery/search \
  -H "Content-Type: application/json" \
  -d '{"region": "Interlagos", "city": "São Paulo", "category": "restaurantes", "max_results": 5}'
```

## O que está implementado

**Fase 0 — Foundation**

- Backend FastAPI com health check e tratamento de erro consistente.
- Schema de banco completo para as entidades estruturais da arquitetura
  v0.2: `Company` (sem depender de identificador externo), `CompanySource`
  (múltiplas fontes por empresa), `Evidence` (proveniência, append-only),
  `AuditSnapshot`, `WebsiteQuality`, `OpportunityScore`, `IdentityMergeLog`,
  `Region`, `Category`.
- Estados não-binários de dado (`confirmed`, `not_detected`,
  `inconclusive`, `inaccessible`, `not_checked`, `stale`) como enum
  reutilizável — nenhuma checagem de presença digital pode colapsar
  "não verificado" em "não existe".
- Configuração centralizada via variáveis de ambiente, sem nenhum segredo
  real versionado. Logging estruturado com `request_id` por requisição.
- Abstração de job (`Job`, `JobContext`) e conexão com a fila Redis/RQ.

**Fase 1 — Discovery**

- `DiscoveryQuery`: validação de entrada com limites internos rígidos
  (raio, resultados, páginas) que nenhuma configuração consegue ultrapassar.
- `GooglePlacesProvider`: Text Search e Nearby Search da Google Places API
  **New** (não a Legacy), com FieldMask mínimo justificado campo a campo,
  timeout configurável, retry limitado com backoff exponencial só para
  erros transitórios, tratamento explícito de 429/4xx/5xx, e paginação
  conforme a documentação oficial (ver `docs/discovery.md`).
- `DiscoveryService`: orquestra `SearchRun -> provider -> normalização ->
  persistência`, nunca decide identidade definitiva nem qualidade/
  oportunidade — só descobre e registra candidatos.
- Persistência compatível com a arquitetura v0.2: `Company` continua sem
  depender de identificador externo; cada fonte vira uma `CompanySource`;
  cada campo observado vira uma `Evidence` append-only; nenhum campo
  ausente na resposta do provider vira uma evidência negativa.
- `SearchRun` com estados não-binários de execução (`pending`, `running`,
  `completed`, `partially_completed`, `failed`, `cancelled`) e
  `ProviderUsageRecord` para rastrear custo por chamada (sem nenhum preço
  fixo no código).
- Cache best-effort e API HTTP (`POST /api/discovery/search`,
  `GET /api/discovery/runs/{id}`).
- Migrations Alembic (2, aplicadas e testadas) e 89 testes ao todo (21 da
  Fase 0 + 68 do domínio `discovery`); destes últimos, 67 rodam por padrão
  com mocks/fakes — nenhum chama a API real — e 1 é um teste de integração
  real, opcional, explicitamente marcado e ignorado por padrão.

## O que NÃO está implementado ainda

- Identity Resolution: nenhuma fusão automática entre `CompanySource` de
  fontes diferentes; a tabela `DedupCandidate` da arquitetura v0.2 ainda
  não foi criada — é escopo da Fase 2.
- Digital Audit (nenhuma checagem própria de site/rede social além do que
  a Google Places já retorna como campo estruturado).
- Website Quality Score e Opportunity Score (as tabelas existem, vazias —
  nenhuma fórmula foi implementada).
- Sales Brief e qualquer agente de IA (nenhuma chamada à API da Anthropic;
  o próprio Discovery é inteiramente determinístico).
- Outros providers de Discovery (OpenStreetMap fica documentado como
  extensão futura, não implementada — ver `docs/discovery.md`).
- Prototype Builder e CRM.
- Dashboard/frontend.
- SSRF protection completa (documentada como obrigatória para a Fase 3,
  quando o sistema passar a buscar URLs arbitrárias de terceiros — o
  Discovery só chama endpoints fixos e conhecidos do Google, nunca uma URL
  fornecida por uma empresa).

## Limitações conhecidas

A máquina usada para esta implementação não tem Docker, WSL, PostgreSQL
nem Redis instalados — apenas Python e Node. Por decisão explícita, isso
teve consequências práticas:

1. Os testes automatizados validam o schema e a lógica de modelo contra
   **SQLite**, aplicando as migrations reais do Alembic — não contra
   PostgreSQL.
2. `docker compose up` **não foi executado** nesta implementação.
3. `POST /api/discovery/search` sempre roda em modo síncrono de fallback
   nesta máquina (sem Redis para enfileirar de verdade) — o caminho
   enfileirado (RQ) está implementado e testado quanto ao *fallback*, mas
   nunca foi exercitado ponta a ponta com um worker real.
4. Nenhuma chamada real à Google Places API foi feita — não há chave de
   API disponível neste ambiente. O provider foi implementado e testado
   contra a documentação oficial com respostas simuladas
   (`httpx.MockTransport`); um teste de integração real e opcional existe
   em `tests/discovery/test_google_places_live.py` para quem tiver uma
   chave própria.

Nenhuma decisão de arquitetura foi alterada por causa dessas limitações —
são lacunas de validação de ambiente, documentadas para serem fechadas
assim que houver Docker/Redis/uma chave de API disponíveis, não mudanças
de design. Ver `docs/development.md` e `docs/discovery.md` para o detalhe
de cada uma.

## Próxima fase

**Fase 2 — Identity Resolution + deduplicação**, conforme o roadmap da
arquitetura v0.2. Não inicia automaticamente: aguarda aprovação explícita.
