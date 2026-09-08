# Guia de desenvolvimento — Fase 6

## Ambiente em que as Fases 0-6 foram implementadas (e por que isso importa)

A máquina usada tem **Python 3.14** e **Node**, mas **não tem Docker, WSL,
PostgreSQL nem Redis instalados**. Isso foi verificado diretamente (não
presumido) antes de começar a Fase 0, e o usuário optou explicitamente por
não instalar nada disso. As Fases 1-6 herdam a mesma limitação —
consequências práticas, documentadas para quem continuar este projeto:

1. **Os testes automatizados rodam contra SQLite**, não PostgreSQL. O
   Alembic aplica a migration real (`alembic upgrade head`) contra um
   arquivo SQLite temporário — isso valida que a migration executa e que o
   schema resultante sustenta os modelos, mas **não** valida
   comportamento específico do PostgreSQL (ex.: `ENUM` nativo — que nem é
   usado, ver `data-model.md`), locking, `JSONB`, extensões como
   `pg_trgm` que fases futuras vão precisar).
2. **`docker compose up` não foi executado nem validado nesta máquina.**
   O `docker-compose.yml` e o `backend/Dockerfile` foram escritos e
   revisados manualmente, mas ninguém os rodou de fato. Antes de confiar
   neles, rode `docker compose up --build` em uma máquina com Docker e
   confirme que os três serviços sobem e `/health` responde.
3. **`enqueue_or_run_discovery()`/`enqueue_or_run_audit()` nunca
   exercitaram o caminho enfileirado de verdade.** Sem Redis, toda chamada
   a `POST /api/discovery/search` ou `POST /api/audit/{company_id}` nesta
   máquina passa pelo fallback síncrono (ver `docs/discovery.md` e
   `docs/digital-audit.md`). O caminho `queue.enqueue(...)` está
   implementado e coberto por testes que validam que o *fallback* funciona
   quando a fila falha, mas ninguém confirmou ainda, com um Redis e um
   worker do RQ reais, que um job enfileirado é de fato processado por um
   worker separado.
4. **O Digital Audit (Fase 3) foi validado com uma chamada de rede real**
   contra `https://example.com` (o domínio reservado pela IANA para esse
   tipo de teste) — não contra um site de empresa de verdade, e não em
   volume. Ver `docs/digital-audit.md`.
5. **Nenhuma chamada real ao provider de IA do Sales Brief (Fase 4) foi
   feita** — não há `ANTHROPIC_API_KEY` disponível nesta máquina. A Fase 4
   foi validada de ponta a ponta (servidor real, banco real, Opportunity
   Score real contra o mesmo `AuditSnapshot` de `https://example.com`
   acima) com um provider MOCKADO injetado diretamente no
   `SalesBriefService` — nunca uma chamada de rede real à Anthropic. O
   caminho de degradação graciosa (sem chave configurada) também foi
   validado de verdade, já que é exatamente o estado real desta máquina.
   Ver `docs/sales-brief.md`.
6. **O Dashboard (Fase 5) foi validado com um servidor Next.js de produção
   real (`npm run build && npm run start`) apontando para um backend real**
   nesta mesma máquina — não só em ambiente de desenvolvimento (`npm run
   dev`). Ver `docs/dashboard.md` para a lista completa do que foi
   exercitado manualmente (listagem, detalhe, filtros, nova pesquisa,
   Sales Brief mockado, estados de erro/vazio, ausência de segredos nos
   artefatos estáticos gerados).
7. **O Prototype Builder (Fase 6) não tem autenticação** — uma auditoria
   confirmou que nenhuma fase do Prospect AI implementou login/sessão/
   JWT, então `Prototype.owner_id` existe mas não isola nada nesta fase
   (mesmo backend aberto de sempre). Validado com o mesmo servidor Next.js
   de produção + backend real da Fase 5: criação, edição da árvore de
   componentes, validação de segurança (tipo fora do catálogo, prop
   aninhada) rejeitada sem corromper o protótipo, exclusão, e ausência de
   segredos no bundle. Ver `docs/prototype-builder.md`.

Se você tem Docker disponível, a validação completa (Postgres real, Redis
real, `docker compose up`, um worker do RQ real) é o próximo passo
recomendado antes de iniciar a Fase 7.

## Pré-requisitos

- Python 3.12 ou superior (testado com 3.14).
- Docker + Docker Compose, para rodar com PostgreSQL/Redis reais
  (opcional para desenvolvimento pontual do schema, mas necessário para
  qualquer fase que de fato converse com um banco Postgres ou uma fila
  Redis real).

## Configuração

```bash
cd backend
cp .env.example .env
# edite .env se necessário — nenhum valor de exemplo é um segredo real
```

**Achado real (Prompt 11 — a primeira vez que este comando foi executado
de verdade nesta sessão, para testar a geração de Prototype contra a
Anthropic API real)**: um `backend/.env` real com uma `ANTHROPIC_API_KEY`
de verdade preenchida quebrou silenciosamente vários testes que esperavam
"nenhuma API key configurada" (`test_*_without_api_key_degrades_gracefully`,
`test_settings_never_default_a_real_secret`, etc.) — porque nada em
`tests/conftest.py` isolava a suíte de um `.env` local antes disso. Já
corrigido: `Settings.model_config` (`app/core/config.py`) pula a leitura
de qualquer `.env` quando `APP_ENV=test` (sempre definida por
`conftest.py` antes de qualquer import de `app`), então um `backend/.env`
real — com uma chave real, para testar contra a API de verdade — nunca
mais afeta a suíte automatizada, independente do que ele contenha.

## Rodando com Docker (recomendado quando disponível)

```bash
docker compose up --build
```

Sobe PostgreSQL, Redis e o backend (que aplica as migrations
automaticamente antes de iniciar o Uvicorn). A API fica em
`http://localhost:8000`.

## Rodando o backend sem Docker

Requer PostgreSQL e Redis acessíveis nos endereços configurados em `.env`.

```bash
cd backend
python -m venv .venv
# Windows (Git Bash): source .venv/Scripts/activate
# Windows (PowerShell): .venv\Scripts\Activate.ps1
# Linux/Mac: source .venv/bin/activate
pip install -r requirements-dev.txt

alembic upgrade head
uvicorn app.main:app --reload
```

## Rodando os testes

```bash
cd backend
pip install -r requirements-dev.txt  # se ainda não instalado
pytest -v
```

Os testes **não** exigem PostgreSQL/Redis reais — `tests/conftest.py`
aponta `DATABASE_URL` para um arquivo SQLite temporário e aplica as
migrations reais nele antes da suíte rodar. O teste
`test_health_dependencies_reports_redis_failure_without_masking_it` inclusive
depende de não haver um Redis real disponível na porta usada — ele existe
para provar que o endpoint de diagnóstico reporta a falha de dependência
honestamente, em vez de mascará-la. Nenhum teste do domínio `discovery`
(`tests/discovery/`) chama a API do Google de verdade — todos usam
`httpx.MockTransport` ou um provider falso, exceto o teste marcado
`@pytest.mark.external`, que é ignorado por padrão (ver `docs/discovery.md`).
Da mesma forma, nenhum teste do domínio `audit` (`tests/audit/`) faz uma
requisição de rede real — SSRF é testado com um resolver de DNS falso
injetado, e o HTTP com `httpx.MockTransport` (ver `docs/digital-audit.md`).
A única chamada de rede real ao Digital Audit nesta implementação foi a
validação manual descrita ali, fora do pytest. Nenhum teste do domínio
`briefing` (`tests/briefing/`) chama a API da Anthropic de verdade —
`test_providers.py` usa `httpx.MockTransport`, e `test_service.py`/
`test_api.py` injetam um provider fake (ou dependem da ausência de
`ANTHROPIC_API_KEY` no ambiente de teste para exercitar o caminho de
degradação graciosa) — ver `docs/sales-brief.md`. O domínio `prototypes`
(`tests/prototypes/`) não faz nenhuma chamada externa — é validação pura
de estrutura de dados (catálogo de tipos, ciclos, profundidade) mais CRUD
contra o SQLite de teste, sem IA e sem rede.

Se `tests/discovery/` parecer lento na sua máquina, é o mesmo motivo do
item 3 acima: cada tentativa de usar o cache best-effort do Discovery
(`app/domains/discovery/cache.py`) tenta conectar ao Redis configurado nos
testes (`redis://localhost:6399/0`, uma porta sem serviço). O cliente
Redis usa um timeout de socket curto (`app/jobs/queue.py`) exatamente para
que isso falhe rápido em vez de travar — se notar lentidão de qualquer
forma, é o primeiro lugar a investigar.

## Rodando uma busca de Discovery localmente

Com o backend no ar (`uvicorn app.main:app --reload`) e uma
`GOOGLE_MAPS_API_KEY` real configurada em `backend/.env`:

```bash
curl -X POST http://localhost:8000/api/discovery/search \
  -H "Content-Type: application/json" \
  -d '{"region": "Interlagos", "city": "São Paulo", "category": "restaurantes", "max_results": 5}'
```

A resposta traz o `id` do `SearchRun`. Sem Redis disponível (como nesta
máquina), a busca já roda de forma síncrona antes de a resposta voltar; com
Redis, consulte o resultado depois em:

```bash
curl http://localhost:8000/api/discovery/runs/<id>
```

Sem `GOOGLE_MAPS_API_KEY` configurada, a chamada continua respondendo
`202` — o `SearchRun` volta com `status: "failed"` e uma mensagem de erro,
nunca um 500. Ver `docs/discovery.md` para o fluxo completo, os limites
internos e o teste opcional contra a API real.

## Inspecionando uma decisão de Identity Resolution

`POST /api/identity/resolve` é só leitura — não precisa de uma busca de
Discovery rodando, nem de API key nenhuma:

```bash
curl -X POST http://localhost:8000/api/identity/resolve \
  -H "Content-Type: application/json" \
  -d '{"source": "openstreetmap", "external_id": "node/1", "name": "REST. SAO JOAO", "phone": "+5511987654321"}'
```

Devolve a decisão (`match`/`no_match`/`inconclusive`), a confiança, as
razões e, se houver, o `matched_company_id` — sem persistir nada. Ver
`docs/identity-resolution.md` para os sinais usados e os limiares
configuráveis.

## Rodando uma auditoria digital localmente

Precisa de uma `Company` que já tenha uma `Evidence` de `field="website"`
(produzida por uma busca de Discovery real, ou inserida manualmente para
teste). Nenhuma API key é necessária — o Digital Audit não depende de
nenhum provedor externo, só faz uma requisição HTTP direta ao candidato:

```bash
curl -X POST http://localhost:8000/api/audit/<company_id>
curl http://localhost:8000/api/audit/<company_id>
```

A resposta inclui `site_state`, `status` e, quando o site foi confirmado
como acessível, o `website_quality` completo (score, componentes por
dimensão, sinais, limitações). Ver `docs/digital-audit.md` para os estados
possíveis e a metodologia do score. **Use apenas destinos seguros e
públicos ao testar manualmente** — nunca aponte para um site de terceiro
sem necessidade real de auditá-lo.

## Calculando um Opportunity Score localmente

Precisa de uma `Company` com pelo menos uma auditoria (`AuditSnapshot`) já
executada — rode `POST /api/audit/{company_id}` primeiro:

```bash
curl -X POST http://localhost:8000/api/scoring/<company_id>
curl http://localhost:8000/api/scoring/<company_id>
```

Nenhuma API key é necessária — o cálculo é inteiramente local e
determinístico (`app.domains.scoring.scoring`), sem chamar nada externo.
A resposta traz `score`, `tier`, `confidence` e o `breakdown` completo por
dimensão. Ver `docs/opportunity-scoring.md`.

## Gerando um Sales Brief localmente

Precisa de um Opportunity Score já calculado (passo anterior). Requer
`ANTHROPIC_API_KEY` configurada em `backend/.env` para de fato gerar
conteúdo — sem ela, o endpoint responde `202` normalmente, com
`status: "failed"` e `error_code: "ProviderUnavailableError"` (nenhum
crash, nenhum briefing inventado — ver `docs/sales-brief.md`):

```bash
curl -X POST http://localhost:8000/api/sales-brief/<company_id>
curl http://localhost:8000/api/sales-brief/<company_id>
```

**Nunca configure uma `ANTHROPIC_API_KEY` real só para "testar" neste
repositório sem necessidade** — cada chamada bem-sucedida é uma chamada
paga de verdade à API da Anthropic.

## Rodando o Dashboard (frontend) localmente

Requer Node.js 20+ (testado com Node 24) e o backend já no ar (padrão:
`http://localhost:8000`).

```bash
cd frontend
cp .env.example .env.local   # ajuste API_BASE_URL se o backend não estiver em localhost:8000
npm install
npm run dev
```

Abre em `http://localhost:3000`. Nenhuma API key passa pelo frontend — ele
só conversa com o backend Python, nunca diretamente com Google/Anthropic
(ver `docs/dashboard.md`, seção "Segurança").

```bash
npm run build && npm run start   # build de produção
npm run lint                     # ESLint
npm run test                     # Vitest — ver docs/dashboard.md, seção "Testes",
                                  # para o que fica de fora e por quê
```

## Usando o Prototype Builder localmente

Requer o frontend (Fase 5) e o backend já no ar.

```bash
curl -X POST http://localhost:8000/api/prototypes   -H "Content-Type: application/json"   -d '{"name": "Landing de teste", "description": "Ideia inicial"}'
```

Ou pela interface: abra `http://localhost:3000/prototypes`, clique em
"Novo protótipo", e depois de criado use o canvas (adicionar/selecionar/
editar/remover/reordenar componentes, alternar preview, salvar). Nenhuma
API key é necessária — o Prototype Builder é inteiramente determinístico,
sem IA (ver `docs/prototype-builder.md`).

## Criando uma nova migration

Sempre que um modelo em `app/domains/*/models.py` mudar:

```bash
cd backend
alembic revision --autogenerate -m "descrição da mudança"
```

Revise o arquivo gerado em `migrations/versions/` antes de aplicar — o
autogenerate do Alembic é um ponto de partida, não a palavra final,
especialmente para mudanças em `Enum` ou em constraints.

## Estrutura de diretórios

```
backend/
  app/
    core/                  # config, logging, erros, middleware
    api/routes/            # health, discovery, identity, audit, scoring, sales_brief, companies, prototypes
    db/                    # base declarativa, sessão, registro de modelos
    domains/
      discovery/           # DiscoveryQuery, DTO, normalização, service, jobs, cache
        providers/         # contrato + GooglePlacesProvider
      identity/            # matching, profile, service (Fase 2)
      audit/               # ssrf, http_client, html_signals, scoring, service, jobs (Fase 3)
      scoring/             # ScoringContext, compute_opportunity_score, service (Fase 4)
      briefing/            # prompt, schemas, providers/, service, jobs (Fase 4)
      companies/           # models + queries.py (agregação de leitura, Fase 5)
      prototypes/          # models, schemas (validação da árvore), service (Fase 6)
      evidence/
    jobs/                  # abstrações de job e conexão com a fila
  migrations/              # Alembic (6 migrations)
  tests/
    discovery/             # testes do domínio discovery (sem chamadas reais)
    identity/              # testes do domínio identity (sem chamadas reais)
    audit/                 # testes do domínio audit (sem chamadas reais)
    scoring/               # testes do domínio scoring (puros + integração, sem IA)
    briefing/              # testes do domínio briefing (provider sempre mockado/fake)
    companies/             # testes das consultas/API agregada do Dashboard (Fase 5)
    prototypes/            # testes de validação da árvore, CRUD e API (Fase 6)
frontend/          # Dashboard (Fase 5) + Prototype Builder (Fase 6) — Next.js
  src/
    app/             # rotas (App Router): dashboard, prospects, pesquisas,
                     # prototypes, configuracoes
    components/      # ui/ (shadcn), badges/, layout/, dashboard/, prospects/,
                     # prospect-detail/, discovery/, prototype-builder/, shared/
    lib/             # api/ (cliente HTTP server-only + tipos), prototype/
                     # (catálogo de componentes), format.ts, utils.ts
infra/           # notas de infraestrutura (o docker-compose.yml fica na raiz)
docs/            # este diretório
```

## Por que não há `poetry`/`pipenv`

A máquina de desenvolvimento não tinha nenhum gerenciador de pacotes
Python além do `pip` padrão. Um `requirements.txt` com versões travadas
(`==`) cobre a necessidade real desta fase (instalação reprodutível) sem
introduzir uma ferramenta adicional. Revisitar essa escolha faz sentido se
o projeto crescer a ponto de precisar de grupos de dependências mais
complexos do que "produção" e "desenvolvimento".
