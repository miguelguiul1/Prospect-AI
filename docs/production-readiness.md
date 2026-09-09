# Production Readiness — Fase 8

Este documento cobre o que a Fase 8 realmente implementou: CI/CD, worker de
background jobs, hardening de segurança/rate limiting, staging integrado,
observabilidade, e as estratégias de backup/recovery e resposta a
incidentes. Cada seção só existe aqui depois de o item correspondente estar
implementado — nada é documentado como pronto antes de estar.

Ver também `docs/crm.md` (Fase 7) e a auditoria `F8.0` (histórico de sessão)
para o contexto que motivou cada decisão desta fase.

## CI/CD (F8.1)

Pipeline em `.github/workflows/ci.yml`, dois jobs paralelos:

- **backend**: instala dependências, roda a suíte completa (`pytest -q`,
  contra SQLite — mesmo padrão de `tests/conftest.py` desde a Fase 0),
  aplica as migrations reais (`alembic upgrade head`) contra um serviço
  `postgres:16-alpine` **real** fornecido pelo runner do GitHub Actions, e
  roda `tests/infra/` (novo nesta fase) contra esse mesmo PostgreSQL real e
  um serviço `redis:7-alpine` real.
- **frontend**: `npx tsc --noEmit`, `npm run lint`, `npm test -- --run`,
  `npm run build`, `npm audit --audit-level=critical`.

Qualquer falha em qualquer etapa bloqueia o merge — é a primeira vez que a
qualidade deste projeto deixa de depender inteiramente de disciplina
manual.

**Importante sobre validação (na própria Fase 8):** o arquivo YAML foi
validado estruturalmente (`yaml.safe_load`, parse sem erro, jobs/steps
presentes como esperado) e todo comando referenciado já havia sido
executado manualmente com sucesso naquela sessão. A execução real do
workflow em si — o GitHub Actions de fato rodando os containers de
serviço e reportando verde — nunca tinha sido observada, porque nenhum
push havia sido feito durante a Fase 8 (regra explícita daquela fase).

**Atualização (Prompt 14) — a execução real do workflow foi observada, e
está falhando:** pushes aconteceram nos Prompts 10-13 (commits `81e4820`
até `2f5ada6`, verificado via API pública do GitHub —
`gh` CLI não está instalado nesta máquina). Todas as 5 execuções de CI
registradas até agora **falharam** (`conclusion: failure`), nos dois jobs
(`Frontend` e `Backend`), consistentemente desde o primeiro push (Prompt
10). Isto NÃO é o mesmo "nunca observado" documentado acima — o workflow
roda, mas está vermelho. A causa raiz específica não foi determinada
nesta sessão: os logs completos de cada step exigem autenticação
(`gh auth login` ou um token) que esta sessão não tem; a API pública sem
autenticação só expõe que a falha acontece no step "Install dependencies"
(Frontend) e no step "Run test suite" (Backend), sem o texto do erro em
si. Ver a seção "Estado do CI/CD Real (Prompt 14)" para o que falta para
diagnosticar e o que precisa do usuário.

### `tests/infra/` — testes contra infraestrutura real

Dois arquivos novos, com uma regra em comum: cada um usa sua própria
variável de ambiente (`REAL_POSTGRES_URL`/`REAL_REDIS_URL`), independente
do `DATABASE_URL`/`REDIS_URL` que o resto da suíte já fixa como SQLite/porta
morta antes de qualquer import (ver `tests/conftest.py`). Se a infraestrutura
real não responder, a suíte inteira do arquivo é pulada com um motivo
explícito — nunca falha silenciosamente, nunca finge sucesso.

Em desenvolvimento local sem PostgreSQL/Redis reais (a situação de toda
máquina usada no projeto, F0 a F8): as verificações destes dois arquivos
aparecem como `skipped`, nunca como `passed`. Em CI, com os serviços reais
do workflow acima, elas executam de verdade.

**Atualização (Prompt 14)**: esta limitação deixou de valer para a máquina
de desenvolvimento atual — PostgreSQL 18 e Redis (via Memurai Developer)
foram instalados nativamente no Windows (não Docker/WSL2; ver seção
"Validação Real Contra Infraestrutura Nativa" abaixo para o porquê e os
resultados). As 12 verificações destes arquivos agora rodam e passam
localmente também, não só em CI.

`test_real_postgres.py` prova, contra PostgreSQL real: conectividade,
versão mínima, que todas as tabelas F0-F7 existem após a migration real,
que o índice único parcial `uq_opportunities_company_open` existe e é
realmente parcial (tem `WHERE`), e — o achado mais importante — que duas
transações concorrentes mudando o mesmo `stage` de uma Opportunity não têm
nenhum lock e a última a committar vence silenciosamente (confirma
empiricamente o achado da auditoria F8.0, seção 14, que antes era só
dedução por revisão de código). Também prova que o índice parcial
realmente rejeita duas linhas `OPEN` concorrentes para a mesma empresa.

`test_real_redis.py` prova, contra Redis real, o caminho que a suíte
principal nunca conseguiu testar (só o inverso — Redis ausente → fail-open,
extensivamente testado desde F7): com Redis presente, o rate limiter
realmente permite dentro do limite, realmente bloqueia acima dele,
realmente expira a janela, e isola corretamente chaves diferentes.

## RQ Worker (F8.2)

**Antes desta fase, não existia nenhum processo consumindo as filas Redis**
(achado da auditoria F8.0, seção 10) — as classes `DiscoveryJob`/
`DigitalAuditJob`/`SalesBriefJob` declaradas desde a Fase 0 nunca foram
instanciadas por nenhum código real; todo `queue.enqueue(...)` sempre
chamou uma função de módulo simples diretamente. Essas classes (e a
abstração `app.jobs.base.Job`/`JobContext` que as sustentava) foram
**removidas** nesta fase — eram código morto que documentava um mecanismo
de retry/correlação que nunca esteve conectado a nada; mantê-las seria
mais enganoso do que não ter nada.

`backend/app/worker.py` é o entrypoint real (`python -m app.worker`):
conecta ao Redis configurado e processa as três filas reais do projeto
(`discovery`, `audit`, `briefing` — nomes sincronizados manualmente com a
constante `QUEUE_NAME` em cada `app/domains/*/jobs.py`, e verificados por
teste, ver abaixo). Sem retry automático por padrão, mesma decisão
deliberada de cada domínio (evitar duplicar uma chamada paga a uma API
externa). Shutdown gracioso vem de graça da própria biblioteca RQ
(SIGINT/SIGTERM já tratados por `Worker.work()`) — nenhum código de sinal
próprio foi adicionado.

Registrado como serviço `worker` em `docker-compose.yml` (Fase 8.2/8.4),
reaproveitando a mesma imagem do backend com um `command` diferente.

**Validação (nunca simulada como real):**

- `tests/jobs/test_worker_integration.py` — **VALIDADO COM MOCK**
  (`fakeredis`, dependência de teste em `requirements-dev.txt`, nunca de
  produção). Prova, pela primeira vez no projeto: um job enfileirado é
  realmente executado por um worker; um worker ouvindo outra fila nunca o
  pega; uma falha marca o job como `FAILED` sem perder o erro, sem retry
  automático; os nomes de fila do worker e de cada domínio batem
  exatamente (teste dedicado de consistência, para nunca mais silenciosamente
  esquecer uma fila nova aqui).
- Execução real do worker contra Redis real: **VALIDADO (Prompt 14)** —
  `tests/infra/test_real_worker.py` enfileira um job real numa fila Redis
  real e um `SimpleWorker` RQ real (burst mode, não `fakeredis`) o executa
  de ponta a ponta; passou nesta sessão contra Redis nativo (Memurai) nesta
  máquina. O workflow de CI (F8.1) ainda não tem uma etapa dedicada que
  suba `python -m app.worker` como processo separado e observe-o consumir
  a fila — a lacuna que resta é só essa (o mecanismo enqueue→worker→execução
  em si já está provado real).
- **Correção (sessão do launcher local, depois do Prompt 15)**: a validação
  acima usava `SimpleWorker` — o próprio entrypoint de produção
  (`python -m app.worker`, que usa `rq.Worker`, não `SimpleWorker`) só foi
  executado pela primeira vez de verdade nesta sessão seguinte, ao montar
  `iniciar-prospect-ai.bat`. Resultado real: **crashou no primeiro job**
  (`AttributeError: module 'os' has no attribute 'fork'`) — `rq.Worker`
  isola cada job via `os.fork()`, inexistente no Windows. Ou seja, a frase
  acima ("o mecanismo... já está provado real") estava certa só para o
  RQ em si via `SimpleWorker`, não para o entrypoint real que
  `docker-compose.yml`/o launcher local de fato invocam. Corrigido:
  `app/worker.py` agora seleciona `SimpleWorker` só em `sys.platform ==
  "win32"`, preservando `Worker` (isolamento por processo — um job que
  trava/estoura memória não derruba o worker inteiro) em produção real
  (Linux, onde `os.fork()` funciona). Validado de ponta a ponta com o
  entrypoint real, não um teste isolado: uma busca de Discovery
  enfileirada com Redis real e nenhum worker rodando ficou presa em
  `PENDING` (reprodução do bug ao vivo); com o worker corrigido no ar,
  uma busca nova foi de `pending` a `failed` (Google Places rejeitando a
  chave placeholder do `.env` — esperado, não é o achado) em ~1 segundo,
  `started_at`/`finished_at` preenchidos. 2 testes novos
  (`tests/jobs/test_worker_entrypoint.py`, isolados via subprocesso — a
  classe é decidida uma vez, no import do módulo) travam a seleção por
  plataforma contra regressão.

## Rate Limiting endurecido + Security Hardening (F8.3)

**Política de Redis indisponível diferenciada por criticidade** (antes: uma
única política "fail-open" para tudo, achado confirmado ao vivo na
auditoria F7.5/F8.0). `app.core.rate_limit.check_and_increment` ganhou um
parâmetro `on_unavailable`:

| Operação | Política | Por quê |
|---|---|---|
| Login | `local_fallback` | Negar login por completo por uma dependência opcional fora do ar seria pior que o risco mitigado — usa um contador local em memória do processo como segunda linha de defesa, **nunca equivalente a um limite distribuído real** (não coordena entre réplicas, é perdido a cada restart). **Risco aceito formalizado em `docs/adr/011-rate-limiter-distribuido.md` (Prompt 10)**: só passa a importar de verdade no dia em que uma segunda réplica do backend existir — nenhuma existe hoje. |
| Registro de conta | `local_fallback` | Mesma razão do login; novo (não existia limite nenhum antes da Fase 8.3). |
| Geração de Outreach | `fail_closed` | Custo financeiro direto (chamada à Anthropic) — bloquear é mais seguro que permitir sem limite. |
| Geração de Sales Brief | `fail_closed` | Mesma razão — **era a única operação de IA do projeto inteiro sem nenhum rate limit** antes desta fase (achado R11 da auditoria F8.0). Por não ter autenticação (rota pré-F7), o limite é por `company_id`, não por usuário. |

Validado com `fakeredis`? Não para este item específico — a suíte usa
Redis genuinamente indisponível (porta morta, mesmo padrão desde F7) para
provar as duas políticas na prática: `tests/test_security_hardening.py`
implicitamente, e testes dedicados em `tests/briefing/test_api.py`/
`tests/outreach/test_api.py` (`TestRateLimiting`) provam que, sem Redis,
Sales Brief e Outreach retornam 429 real (fail-closed), não um 202/201
mascarando a ausência de controle.

**Fail-fast de configuração em produção** (`app.main._validate_production_config`,
achado R5): antes desta fase, subir com `JWT_SECRET_KEY` no valor padrão
inseguro ou com `CORS_ALLOW_ORIGINS=["*"]` em `APP_ENV=production` só
gerava um log de aviso — nada impedia o processo de subir mesmo assim.
Agora levanta `RuntimeError` antes de qualquer rota existir.

**Security headers** (`X-Content-Type-Options`, `X-Frame-Options`,
`Referrer-Policy`, `Strict-Transport-Security`) em toda resposta — backend
via `SecurityHeadersMiddleware` (`app.core.middleware`) e frontend via
`next.config.ts` (`headers()`). Sem CSP própria — decisão deliberada, ver
comentário em `next.config.ts`: uma CSP mal ajustada quebraria produção
silenciosamente sem o mesmo nível de teste do resto do projeto.

**Limite de tamanho de requisição** (`RequestSizeLimitMiddleware`, achado
R7): rejeita com 413 qualquer requisição cujo `Content-Length` declarado
exceda `MAX_REQUEST_BODY_BYTES` (default 1 MB) — antes de o corpo começar a
ser lido. Não cobre requisições chunked sem `Content-Length` (nenhum
endpoint do projeto usa isso hoje); os limites de campo do Pydantic
continuam sendo a segunda linha de defesa nesse caso residual.

**CSRF**: reavaliado, nenhuma mudança de código feita — a arquitetura já
protege estruturalmente (o backend FastAPI nunca lê um cookie de sessão
diretamente; o token só chega como `Authorization: Bearer`, montado pelo
servidor Next.js a partir do cookie httpOnly — um request forjado
cross-site não teria como incluir esse header). Nenhum ataque simulado
explícito de CSRF foi executado nesta fase.

**Cookies de sessão**: revisados, nenhuma mudança de código — já corretos
por desenho desde a Fase 7 (`httpOnly: true`, `sameSite: "lax"`,
`secure: NODE_ENV === "production"`). Inspeção do header `Set-Cookie` real
via um Server Action ao vivo continua **NÃO VALIDADA** (limitação de
ferramenta desta sessão, não de código).

**Todos os 6 testes que quebraram com a mudança de política de rate
limiting foram corrigidos, não contornados**: os testes de Sales Brief/
Outreach que exercitam OUTRO comportamento (empresa não encontrada,
resposta 202 de falha graciosa, etc.) agora contornam explicitamente o
rate limit via `monkeypatch` (documentado no próprio teste, com um
comentário explicando por quê) — e cada arquivo ganhou um teste dedicado
que desfaz esse contorno para provar o fail-closed de verdade.

## Docker + Staging Integrado (F8.4)

`docker-compose.yml` agora define 5 serviços: `postgres`, `redis`,
`backend`, `worker` (Fase 8.2) e `frontend` (novo). `frontend/Dockerfile`
(novo, multi-stage) usa o build `output: "standalone"` do Next.js
(`next.config.ts`) — validado localmente (`npm run build` gera
`.next/standalone/server.js` corretamente); a construção da imagem em si
permanece **NÃO VALIDADA** (sem Docker nesta máquina, mesma limitação de
sempre). `backend/Dockerfile` ganhou um `HEALTHCHECK` real (usa `/health`,
que nunca toca banco/Redis — seguro como liveness).

**Gap conhecido, deliberadamente não contornado (Prompt 14)**: a
validação de Postgres/Redis desta fase (ver "Validação Real Contra
Infraestrutura Nativa" acima) usou instalação nativa no Windows
especificamente para NÃO precisar de Docker Desktop/WSL2 nesta máquina
(risco de RAM — só ~1GB livre logo após reiniciar, de ~7,7GB no total).
Isso valida Postgres e Redis como dependências de runtime, mas não toca
`docker build`/`docker compose up` em nenhum momento — a construção real
das imagens (`backend/Dockerfile`, `frontend/Dockerfile`) e a
orquestração via `docker-compose.yml` continuam **inteiramente NÃO
VALIDADAS**, exatamente como antes desta sessão. Nenhuma tentativa foi
feita de contornar isso (ex.: simular `docker build` com outra
ferramenta, validar só a sintaxe e chamar de "validado") — continua
honestamente como um gap em aberto, que só se fecha com Docker Desktop
disponível (nesta máquina ou em CI, onde os serviços `postgres`/`redis`
já rodam como containers reais, mas a imagem do PRÓPRIO projeto nunca foi
construída nem lá).

**Por que nenhum healthcheck de container foi criado para o `worker`**: RQ
não expõe nenhum endpoint HTTP para checar; inventar um mecanismo próprio
só para preencher essa lacuna seria mais frágil do que documentar
honestamente a ausência. A observabilidade real de um worker travado
(fila crescendo sem consumo) é um problema de métricas (F8.6), não de
container healthcheck.

### Separação Local / Staging / Production

Nenhum ambiente de staging ou produção real foi provisionado nesta fase
(exigiria conta em nuvem/hospedagem — fora do que uma sessão de
desenvolvimento local pode criar de verdade sem inventar credenciais).
O que existe é a **convenção documentada** que qualquer provisionamento
futuro deve seguir:

| | Local | Staging | Production |
|---|---|---|---|
| Como roda | `docker compose up` (este repo) ou `pytest`/`npm run dev` direto | Deploy real, infraestrutura própria | Deploy real, infraestrutura própria |
| `DATABASE_URL` | `postgres` do compose, ou SQLite (testes) | Banco PostgreSQL dedicado, nunca compartilhado com produção | Banco PostgreSQL dedicado |
| `REDIS_URL` | `redis` do compose | Redis dedicado | Redis dedicado |
| `ANTHROPIC_API_KEY` | Vazio (degrada graciosamente) ou uma chave de teste pessoal | Chave própria de staging, com limite de gasto configurado no provedor | Chave própria de produção |
| `JWT_SECRET_KEY` | Default inseguro (permitido só aqui) | Valor real, único | Valor real, único, diferente do de staging |
| `APP_ENV` | `development` | `production`* | `production` |
| `CORS_ALLOW_ORIGINS` | `localhost:3000` | Domínio real de staging | Domínio real de produção |

<sup>*Staging deveria usar `APP_ENV=production` para exercitar exatamente o
mesmo comportamento de produção (fail-fast de config, logs JSON) — a
diferença entre staging e produção está inteiramente em QUAIS recursos
(banco/Redis/domínio/chave) são apontados, nunca no comportamento do
código.</sup>

**Nada no código hoje impede, por si só, que alguém aponte staging para o
banco de produção por engano de configuração** — não existe uma validação
automática de que as URLs são de fato diferentes entre ambientes (achado
R14 da auditoria F8.0, não corrigido nesta fase — exigiria decidir uma
convenção de nomenclatura/tag que só faz sentido quando os dois ambientes
reais existirem de verdade para testar contra).

## Real Runtime Validation (F8.5)

Estado real de cada dependência externa. As linhas abaixo cobrem a sessão
original da Fase 8 (nenhuma infraestrutura real disponível); ver
"Validação Real Contra Infraestrutura Nativa (Prompt 14)" para a sessão
que finalmente teve Postgres/Redis reais e o que mudou:

| Dependência | Status | Evidência |
|---|---|---|
| PostgreSQL | **VALIDADO AO VIVO (Prompt 14)** | `tests/infra/test_real_postgres.py` (6 testes: conectividade, versão, todas as tabelas F0-F7, índice parcial real, race condition de stage-change, concorrência de criação de Opportunity) — rodou de verdade contra PostgreSQL 18 nativo (Windows) e passou. Segue validado estruturalmente em CI contra `postgres:16-alpine`, mas essa execução de CI específica continua nunca observada (nenhum push foi feito) |
| Redis | **VALIDADO AO VIVO (Prompt 14)** | `tests/infra/test_real_redis.py` (5 testes: rate limiter real) + `tests/infra/test_real_worker.py` (worker RQ contra Redis real, não `fakeredis`) — rodaram contra Redis nativo (Memurai Developer) e passaram. Mesma ressalva de CI acima: validado estruturalmente, execução do workflow em si não observada |
| RQ (worker, mecanismo via `SimpleWorker`) | **VALIDADO COM MOCK** (fakeredis, F8.2) **+ VALIDADO AO VIVO (Prompt 14)**, contra Redis real | `tests/jobs/test_worker_integration.py` + `tests/infra/test_real_worker.py` |
| RQ (entrypoint real, `python -m app.worker`) | **VALIDADO AO VIVO — corrigido depois de crashar (sessão do launcher local)**: `rq.Worker` usa `os.fork()`, inexistente no Windows; crashou no primeiro job real. `SimpleWorker` no Windows (mesma classe da linha acima) corrige; validado com uma busca de Discovery real indo `pending`→`failed` via o entrypoint de produção, não um teste isolado | `app/worker.py`, `tests/jobs/test_worker_entrypoint.py`, ver seção "RQ Worker (F8.2)" acima |
| Anthropic | **NOT VALIDATED — credencial ausente do ambiente do processo, deliberado** | `tests/infra/test_real_anthropic.py`: pula automaticamente sem `ANTHROPIC_API_KEY` no ambiente do processo. `backend/.env` tem uma chave real (Prompt 11), mas o Prompt 14 delimitou o escopo a banco/fila/CI, não ao Generation Engine — a chave não foi exportada para o processo de teste de propósito, nenhuma chamada real foi feita |
| PostgreSQL — concorrência (Opportunity, stage-change) | **VALIDADO AO VIVO (Prompt 14)**, contra Postgres real | Mesmo arquivo acima |
| Redis — restart/reconexão sob operação | **NOT VALIDATED** | Exigiria controlar o ciclo de vida de um processo Redis real (matar/reiniciar) durante uma operação em andamento — ainda não exercitado nesta sessão nem em nenhuma anterior |

**Resumo honesto**: PostgreSQL, Redis e RQ contra Redis real foram
observados funcionando de verdade nesta sessão (Prompt 14), pela primeira
vez no projeto — contra infraestrutura nativa no Windows (não Docker,
decisão deliberada por restrição de RAM da máquina; ver seção dedicada
abaixo). Anthropic continua não validado ao vivo, mas por escopo
deliberado desta fase, não por falta de infraestrutura. O que resta
genuinamente pendente: a execução do workflow de CI em si sendo observada
rodando (exige um push), o failover de Redis sob operação, e a construção
real das imagens Docker/Compose (nenhuma sessão até aqui teve Docker
disponível).

## Validação Real Contra Infraestrutura Nativa (Prompt 14)

A Fase 8 entregou a *capacidade* de validação real (`tests/infra/`), mas
nunca a observou rodando: nenhuma máquina usada no projeto (F0-F8) tinha
PostgreSQL, Redis ou Docker disponíveis. Esta sessão fecha essa lacuna,
mas por um caminho diferente do assumido em toda a Fase 8 — não Docker
Compose, e sim PostgreSQL 18 e Redis (via Memurai Developer, o substituto
nativo mais maduro disponível para Windows — o "Redis on Windows" do
winget é um fork de 2016, versão 3.0, abandonado) instalados diretamente
no SO. Decisão do usuário: a máquina tinha ~1GB de RAM livre logo após
reiniciar (~7,7GB no total) — rodar Docker Desktop + WSL2 nela era um
risco desnecessário para o que a validação exigia. `docker-compose.yml`
continua sendo o caminho documentado para staging/produção (Linux,
containers reais); a instalação nativa é especificamente para
desenvolvimento/validação local nesta máquina, e não substitui a
necessidade de validar a construção real das imagens Docker/Compose em si
(que continua **NÃO VALIDADA** — ver seção "Docker + Staging Integrado" —
porque nenhuma sessão até aqui teve Docker disponível, e esta optou
deliberadamente por não instalá-lo).

**O que foi validado, contra PostgreSQL 18 e Redis (Memurai) reais
rodando nesta máquina:**

- **Migrations, ida e volta completa contra Postgres real**: `alembic
  upgrade head` (as 13 migrations até `0013_prototype_versioning`)
  aplicado com sucesso; `alembic downgrade base` executou os 13
  `downgrade()` em cadeia pela primeira vez contra um banco real (não
  SQLite) — confirmado que só `alembic_version` resta; `alembic upgrade
  head` de novo reconstruiu exatamente as mesmas 24 tabelas (comparação
  linha a linha, sem diferença). Ver "Backup, Recovery e Migrations" para
  o detalhe de que isto foi verificado manualmente, não por um novo teste
  automatizado.
- **`tests/infra/test_real_postgres.py`** (6 testes): todos passando —
  conectividade, versão, as tabelas F0-F7 existem, o índice único parcial
  `uq_opportunities_company_open` existe e é realmente parcial, a race
  condition de stage-change sem lock é observável, a segunda Opportunity
  OPEN concorrente é rejeitada pelo banco.
- **`tests/infra/test_real_redis.py`** (5 testes): todos passando — ping,
  o rate limiter realmente permite dentro do limite, realmente bloqueia
  acima dele, expira a janela, isola chaves diferentes.
- **`tests/infra/test_real_worker.py`** (1 teste): job enfileirado no
  Redis real, executado de ponta a ponta por um `SimpleWorker` RQ real.
- **Suíte completa** (`pytest`, sem nenhuma variável de ambiente extra):
  `701 passed, 3 skipped` — as 12 verificações de infraestrutura real
  acima, mais toda a suíte pré-existente contra SQLite, sem nenhuma
  regressão. Os 3 `skipped` são a Anthropic (ver abaixo) e um skip
  pré-existente não relacionado a esta sessão.
- **Anthropic**: `tests/infra/test_real_anthropic.py` continua pulado —
  fora do escopo desta fase (o objetivo era banco/fila/CI, não o
  Generation Engine); nenhuma chamada real foi feita.

**Dois achados reais desta sessão, ambos corrigidos.** Nenhum dos dois é
um bug de lógica de negócio — são gaps de configuração/suíte só visíveis
com infraestrutura real disponível pela primeira vez:

1. **`backend/.env` `REDIS_URL`: `localhost` → `127.0.0.1`.** Nesta
   máquina Windows, resolver o hostname `localhost` custa ~220ms de forma
   consistente (medido: 5 tentativas, 202-233ms cada) — o suficiente para
   estourar o timeout de 0.2s que `app/jobs/queue.py:29` usa
   deliberadamente ("falhar rápido quando Redis está ausente"). Com
   `127.0.0.1` (sem resolução de nome), o mesmo round-trip cai para
   ~14ms. Como o redis-py descarta uma conexão após qualquer erro (nunca
   a devolve ao pool), cada tentativa seguinte pagava o mesmo custo de
   resolução de novo — um loop de timeouts reais contra um Redis 100%
   saudável.

   **A causa raiz específica (resolução de `localhost` custar ~220ms) é
   desta máquina/Windows** — em CI (Linux) e dentro da rede interna do
   Docker Compose (que resolve `redis` via DNS interno do Compose, não
   via `localhost`) esse custo específico não existe. **Mas a classe de
   risco é geral e deve ser vigiada em qualquer ambiente futuro, não só
   corrigida aqui**: `get_redis_connection()` (`app/jobs/queue.py:29`)
   define `socket_connect_timeout`/`socket_timeout` em 0.2s, mas essa
   janela cobre só a fase de conexão/leitura do socket — a resolução de
   nome (`getaddrinfo`) acontece ANTES e não é limitada por nenhum dos
   dois timeouts. Qualquer ambiente (staging, produção, um Redis
   gerenciado atrás de um endpoint DNS, um cluster Kubernetes sob DNS
   interno instável) onde `REDIS_URL` aponte para um hostname que
   precise de resolução — não um IP literal nem um nome já cacheado por
   um resolvedor rápido — está exposto exatamente a esta mesma classe de
   falha se a resolução de nome for lenta por qualquer motivo (DNS da
   VPC sob carga, split-horizon DNS, cache frio). O sintoma em produção
   seria silencioso: `check_and_increment` cai em `fail_open`/
   `fail_closed`/`local_fallback` sem nenhum erro visível fora do log
   `rate_limit_check_unavailable` e da métrica
   `rate_limit_redis_unavailable_total` (F8.6) — rate limiting
   efetivamente desativado (ou operações de IA bloqueadas, dependendo da
   política) sem que o Redis em si esteja realmente indisponível.
   **Recomendação para quando um ambiente real existir**: preferir um IP
   literal ou um nome já resolvido por um resolvedor local rápido em
   `REDIS_URL` quando possível (como o Docker Compose já faz, via DNS
   interno), e monitorar `rate_limit_redis_unavailable_total` em produção
   como sinal de que este timeout pode estar apertado demais para o
   ambiente real — não é um problema resolvido de vez, é um limite de
   design que só nunca foi estressado antes desta sessão.
2. **`tests/infra/test_real_redis.py` — `TestRateLimiterAgainstRealRedis`
   nunca havia exercitado Redis real, em nenhuma sessão, nem em CI.** A
   classe chama `check_and_increment` (código de produção), que lê
   `REDIS_URL` via `get_settings()` — mas `tests/conftest.py` fixa
   `REDIS_URL=redis://localhost:6399/0` (porta morta, deliberadamente)
   para a sessão inteira de pytest, sem exceção para `tests/infra/`. Sem
   um fixture que contornasse isso, a classe sempre bateu na porta morta
   e caiu silenciosamente no fail-open — nunca testou o que seu próprio
   docstring afirma testar, desde que foi escrita na Fase 8. Corrigido com
   um fixture `autouse` (`_app_client_targets_real_redis`) que aponta o
   `REDIS_URL` do processo para `REAL_REDIS_URL` e limpa os `lru_cache` de
   `get_settings`/`get_redis_connection` só durante os testes desta
   classe — mesmo padrão de "conexão própria, independente do que o resto
   da suíte fixa" que `test_real_postgres.py` já usava.

`prospect_ai_ci` (o nome de banco que `REAL_POSTGRES_URL` usa por padrão,
para não misturar dados de teste com o banco de desenvolvimento
`prospect_ai`) foi criado e migrado nesta sessão — a partir de agora, um
`pytest` sem nenhuma variável de ambiente extra já valida Postgres e Redis
reais por padrão nesta máquina, não só em CI.

## Estado do CI/CD Real (Prompt 14)

Verificado via API pública do GitHub (`api.github.com`, sem autenticação —
`gh` CLI não está instalado nesta máquina e não há token configurado
nesta sessão). `git status` confirma que `main` local está exatamente em
sincronia com `origin/main` (`up to date`) — os pushes dos Prompts 10-13
realmente aconteceram, ao contrário do que a seção "CI/CD (F8.1)" acima
(escrita antes de qualquer push) documentava.

**As 5 execuções de CI registradas até agora, todas `failure`:**

| Run | Commit | Prompt | Conclusão |
|---|---|---|---|
| 5 | `2f5ada6` | 13 (preview responsivo + chat de refinamento) | failure |
| 4 | `dd3a978` | 12 (refinamento + versionamento) | failure |
| 3 | `617e610` | 11 (validação Anthropic real) | failure |
| 2 | `81e4820` | 10 (fecho dos riscos do F8) | failure |
| 1 | `e961f5b` | f8.9 (patch PyJWT) | failure |

Run mais recente (commit `2f5ada6`, o HEAD atual de `main`):
https://github.com/miguelguiul1/Prospect-AI/actions/runs/34284012645

Os dois jobs falham, sempre no mesmo lugar nas 5 execuções:

- **Frontend** (`typecheck + lint + test + build`): falha no step
  "Install dependencies" — antes mesmo de `tsc`/lint/test/build rodarem.
- **Backend** (`pytest + infra real`): falha no step "Run test suite
  (SQLite — mesmo padrão de `tests/conftest.py`)" — ou seja, na suíte
  `pytest -q` básica contra SQLite, antes mesmo de chegar nas migrations
  reais contra o `postgres:16-alpine` do runner ou em `tests/infra/`.

**Causa raiz de cada job, confirmada pelo usuário lendo o log real na UI
do GitHub (`gh` CLI não está instalado nesta máquina — sem auth, a API
pública só expõe status/conclusão por step, não o texto do log; `GET
.../actions/jobs/{id}/logs` retorna `403 Forbidden` sem token):**

- **Frontend**: conflito de peer dependency. `vitest@5.0.0` exige
  `@types/node: "^22.0.0 || >=24.0.0"`, mas `package.json` fixava
  `@types/node` em `^20`. `npm ci` (usado no CI, estrito por natureza)
  falha nisso; `npm install`/`npm ci` locais toleravam silenciosamente —
  reproduzido nesta sessão com o npm local (11.12.1), que não gerou
  erro algum, contra o npm mais antigo que vem com Node 22 no runner
  (mais estrito). **Corrigido**: `@types/node` `^20` → `^22` (bate com o
  `node-version: "22"` que o próprio workflow já usa), lockfile
  regenerado. Os 4 passos do job Frontend foram replicados localmente
  após a correção (`npm ci` limpo, `tsc --noEmit`, `lint`, `test` —
  187/187 —, `build`), todos passando; `npm audit --audit-level=critical`
  também limpo (0 vulnerabilidades).

- **Backend**: não era ordem de steps nem URL errada — os dois já
  estavam corretos, e essa possibilidade foi ativamente descartada por
  leitura antes de se chegar à causa real (texto idêntico byte a byte
  entre `DATABASE_URL` do step de migration e `REAL_POSTGRES_URL` do step
  de infra; os 13 arquivos de migration rastreados pelo git batem com o
  disco; nenhum `.env` comitado). A causa real: `backend/pyproject.toml`
  tem `testpaths = ["tests"]` e o step "Run test suite (SQLite — mesmo
  padrão de `tests/conftest.py`)" roda `pytest -q` **sem nenhum argumento
  de caminho** — ou seja, apesar do nome, ele coleta a árvore `tests/`
  inteira, `tests/infra/` incluído. `tests/infra/test_real_postgres.py` e
  `test_real_redis.py` têm seus próprios defaults hardcoded
  (`REAL_POSTGRES_URL`/`REAL_REDIS_URL` apontando exatamente para os
  serviços `postgres`/`redis` do job) — que já estão de pé desde antes do
  primeiro step. Resultado: estes testes rodam de verdade **dentro do
  step "SQLite"**, antes do step "Apply migrations" (mais abaixo no
  arquivo) sequer ter começado — batendo num Postgres real mas sem
  nenhuma tabela (nem `alembic_version`), e num Redis real que expõe o
  mesmo bug de fixture do rate limiter descrito acima. O step falha, e
  por isso os dois seguintes ("Apply migrations", "Run infra tests")
  aparecem como `skipped` nas 5 execuções — nunca chegam a rodar.
  **Corrigido**: `pytest -q --ignore=tests/infra` no step "SQLite"
  (`.github/workflows/ci.yml`), para que ele faça só o que o nome promete.
  Validado localmente: `pytest -q --ignore=tests/infra` coleta 690 testes
  (704 − 14, exatamente os de `tests/infra/`) e passa limpo (`689 passed,
  1 skipped`).

Nenhuma das duas causas foi óbvia por leitura superficial — as duas
exigiram reproduzir o comando exato do CI localmente (`npm ci` limpo) e/ou
descartar metodicamente as hipóteses mais simples (ordem de steps, URL
errada) antes de achar a real. Ver commits desta sessão para o diff
completo de cada correção.

**O que ainda não foi observado**: o workflow rodando verde de ponta a
ponta na UI real do GitHub — as correções acima foram validadas pela
melhor aproximação local possível (reprodução exata dos comandos de cada
step), não pela execução real do Actions em si. Isso só se confirma depois
de um push.

## Observabilidade (F8.6)

**Antes desta fase**: nenhuma métrica existia (achado R9 da auditoria
F8.0); `/health/dependencies` marcava `status="degraded"` para uma falha
de Redis — uma dependência tratada como best-effort em todo o resto do
sistema (fail-open no rate limiter, cache que degrada graciosamente) —
inconsistência confirmada na própria F8.0; nenhum log de job carregava
`job_id`; nenhum log de requisição autenticada carregava `user_id`.

**Registro de métricas em processo** (`app/core/metrics.py`, novo,
**zero dependências novas** — decisão deliberada de não trazer
`prometheus_client` para um projeto deste porte): contadores e
histogramas simples, thread-safe (`threading.Lock`), expostos em
formato de texto Prometheus por `GET /metrics` (`app/api/routes/metrics.py`,
sem autenticação — mesmo padrão de `/health`, é infraestrutura de
observabilidade, não dado de negócio). `reset()` existe só para uso em
teste.

Métricas instrumentadas:

| Métrica | Labels | Onde |
|---|---|---|
| `http_requests_total` | `method`, `path` (template de rota, nunca o path resolvido — evita cardinalidade não limitada por UUID real), `status` (`2xx`/`4xx`/`5xx`) | `RequestContextMiddleware` |
| `http_request_duration_ms` (histograma simples: soma + contagem) | `method`, `path` | `RequestContextMiddleware` |
| `ai_requests_total` | `domain` (`sales_brief`/`outreach`), `status` (`completed`/`failed`) | `SalesBriefService`, `OutreachService` |
| `ai_tokens_total` | `domain`, `direction` (`input`/`output`) | Mesmos dois serviços, só quando o provider reporta contagem de tokens |
| `auth_failures_total` | `reason` (`missing_token`/`invalid_token`/`user_not_found_or_inactive`) | `app.domains.auth.dependencies._unauthorized` |
| `rate_limit_redis_unavailable_total` | `policy` (`fail_open`/`fail_closed`/`local_fallback`) | `check_and_increment`, ramo de exceção |

Validação: **VALIDADO ESTATICAMENTE + suíte própria** —
`tests/test_metrics.py` (7 testes) prova o registro isoladamente
(incremento, agregação por label, renderização, reset) e via
`GET /metrics` de ponta a ponta (contagem real de `http_requests_total`
e `auth_failures_total` após requisições reais ao `TestClient`). Nunca
testado contra um Prometheus real fazendo scrape — não há Prometheus
nesta sessão; o formato de saída segue a especificação de texto exposto
do Prometheus por leitura da documentação, não por validação cruzada com
o parser oficial.

**Readiness redesenhado** (`GET /health/dependencies`, achado F8.0 R9
corrigido): antes, qualquer falha (banco OU Redis) produzia o mesmo
`status="degraded"`, sem diferenciar severidade. Agora:

- **PostgreSQL indisponível** → único caso que retorna HTTP 503 e
  `status="not_ready"` — é a única dependência sem a qual o sistema não
  serve nenhuma requisição real.
- **Redis indisponível** → reportado como `"degraded: <TipoDoErro>"` no
  campo `redis`, mas **nunca** rebaixa o `status` geral nem o HTTP code
  (continua 200/`"ok"`) — consistente com o fail-open já usado em todo o
  resto do sistema (rate limiter, cache de Discovery).
- **Anthropic** → reportado apenas como `"configured"`/`"not_configured"`
  (presença da variável de ambiente). Deliberadamente **sem nenhuma
  chamada de rede real** — um readiness probe chamado a cada poucos
  segundos por um orquestrador não deve gerar custo ou latência de API
  externa a cada verificação.

Esta é uma **mudança de comportamento intencional** de um teste
pré-existente (`tests/test_health.py`): a expectativa antiga
(`status=="degraded"`, `"error:"`) estava documentando o comportamento
antigo incorreto, não um contrato correto — corrigida para
`status=="ok"`/`"degraded:"`, com dois testes novos cobrindo o caso de
banco indisponível (503/`not_ready`, simulado via `monkeypatch` no
`Session.execute`, sem precisar de um Postgres real quebrado) e a
ausência de chamada de rede ao checar Anthropic.

**Correlação de logs**: `bind_request_context(user_id=...)` chamado em
`get_current_user` logo após autenticação bem-sucedida — todo log
subsequente da requisição carrega o usuário responsável, sem precisar
reconstruir isso a partir do `request_id` e de uma consulta separada.
`bind_job_context()` (novo, `app.jobs.queue`) usa `rq.get_current_job()`
para vincular `job_id`/`queue_name` a todo log emitido dentro de um
`run_*` de Discovery/Digital Audit/Sales Brief — só tem efeito dentro de
um worker real; no fallback síncrono (`get_current_job()` retorna
`None`), o `request_id` do middleware HTTP já é a correlação válida.

**O que continua fora de escopo**: nenhum sistema de alertas, nenhum
dashboard, nenhum agregador de logs (ELK/Loki), nenhum tracing
distribuído — nenhum dos quatro se justifica para um projeto deste porte
sem um operador real por trás; o `/metrics` em texto Prometheus é
suficiente para um `docker compose` com Prometheus apontado para ele
quando esse dia chegar, sem exigir reescrita.

Regressão completa após F8.6: **514 passed, 15 skipped, 0 failed**
(507 pré-existentes + 7 novos de `tests/test_metrics.py`; a mudança
intencional em `test_health.py` está incluída nesses 514, não é uma
falha).

## Concorrência, Carga e Falhas (F8.7)

### Teste de carga local real (`backend/scripts/load_test.py`)

Script novo, executado manualmente (não faz parte do `pytest`): sobe um
`uvicorn` **real** em processo separado, escutando em uma porta TCP real,
apontado para um arquivo SQLite dedicado e recém-migrado (`alembic upgrade
head` de verdade), e dispara requisições HTTP reais via `httpx` com
`ThreadPoolExecutor` (threads reais do SO, não corrotinas simulando
concorrência). **Rótulo honesto**: mede a camada HTTP/aplicação sob
concorrência real, mas contra SQLite, não PostgreSQL — os números de
throughput/latência não são os de produção (SQLite serializa escritas por
processo; PostgreSQL usa MVCC com locks por linha). Rodado nesta sessão,
resultados reais capturados:

| Cenário | Requisições | Concorrência | Resultado real |
|---|---|---|---|
| `GET /health` (liveness, sem banco) | 300 | 30 threads | 532 req/s, latência média 53.9ms, p95 100.7ms, p99 107.2ms, 0 erros |
| `GET /api/crm/opportunities` (leitura autenticada, com banco) | 150 | 15 threads | 186 req/s, latência média 78.5ms, p95 110.3ms, p99 121.0ms, 0 erros |
| `POST /api/crm/opportunities` concorrente, mesma empresa (prova de corretude) | 15 | 15 threads | 15×201, **0 erros**; verificado por consulta direta ao banco: exatamente **1** Opportunity `OPEN` sobreviveu — o índice único parcial segura a corrida também contra SQLite real, via HTTP real, não só em teoria |
| `POST /api/auth/login` concorrente, credenciais erradas (rate limit sob carga real) | 20 | 20 threads | 10×401 (dentro do limite) + 10×429 (acima do limite de 10/300s) — prova que o contador `local_fallback` (protegido por `threading.Lock`) é de fato thread-safe sob concorrência real de SO, não só correto em um teste sequencial de unidade |

**Achado**: nenhum erro 5xx ou de transporte em nenhum cenário — a camada
HTTP/middleware/ORM não quebra sob esta carga (proporcional a um ambiente
de desenvolvimento local, não "milhões de usuários", conforme escopo desta
fase). O cenário 3 é a prova empírica mais forte já produzida no projeto de
que a idempotência de `create_or_get` funciona sob concorrência real —
antes desta fase, a única prova de concorrência existente
(`tests/infra/test_real_postgres.py`, F8.1) nunca havia sido executada
(exigia PostgreSQL real). Este script, ao contrário, roda de verdade nesta
máquina.

**Limitação documentada, não corrigida**: sob uma carga de escrita muito
mais alta que os 15 requests concorrentes testados aqui, SQLite pode
retornar `database is locked` (lock de escrita único por arquivo) — um
comportamento que PostgreSQL não tem (MVCC). Não é um bug a corrigir no
código de aplicação (que já roda sobre `postgresql+psycopg` em
produção/CI); é uma característica conhecida de usar SQLite como stand-in
de desenvolvimento, já documentada desde a Fase 0.

### Testes de injeção de falha (`backend/tests/test_failure_injection.py`, novo, 4 testes)

Cobrem exatamente o que a cobertura já existente (extensiva desde F7 para
"Redis indisponível", e em `tests/briefing/test_providers.py`/
`tests/outreach/test_service.py` para "Anthropic indisponível") ainda não
cobria:

- **Falha de banco no meio de uma rota de negócio comum** (`GET
  /api/companies`, `GET /api/crm/kpis`) — não só em `/health/dependencies`
  (único lugar já coberto antes): confirma que `unhandled_exception_handler`
  devolve um 500 limpo (`{"error": {"code": "internal_error", ...}}`), sem
  vazar o tipo ou a mensagem real da exceção, também para rotas de negócio
  comuns, não só para o health check desenhado especificamente para isso.
- **Worker down**: um job enfileirado (via `fakeredis`) sem nenhum
  `Worker(...).work()` consumindo a fila permanece `queued` indefinidamente
  — nunca perdido, nunca marcado como falho, nunca executado por engano em
  outro lugar. Complementa (não duplica)
  `tests/jobs/test_worker_integration.py`, que sempre inicia um worker para
  provar o caminho de sucesso/falha de execução.
- Um teste-âncora de documentação (`TestRedisDownConsistencySummary`) que
  importa os quatro módulos onde a cobertura de "Redis indisponível" já
  vive, para que uma remoção futura acidental de qualquer um deles quebre
  visivelmente este arquivo em vez de silenciosamente perder cobertura.

**Metodologia não destrutiva**: nenhum teste derruba um processo real (não
há PostgreSQL/Redis real para derrubar nesta máquina); cada falha é
injetada via `monkeypatch` cirúrgico, documentado em cada teste.

### O que permanece NÃO VALIDADO nesta fase

- Failover real de Redis (matar/reiniciar um processo Redis real durante
  uma requisição em andamento) — exigiria um Redis real e controle do seu
  ciclo de vida, indisponíveis nesta máquina.
- Restart do backend sob carga (impacto real em conexões em andamento) —
  o script de load test para o servidor de forma limpa ao final, nunca o
  interrompe abruptamente no meio de uma rajada.
- Teste de **carga** (`load_test.py`, throughput/latência sob
  `ThreadPoolExecutor`) contra PostgreSQL/Redis reais — os números desta
  seção continuam todos contra SQLite; o script não foi re-executado contra
  Postgres real. Diferente disto, os testes de **corretude sob
  concorrência** de `tests/infra/` (race condition de stage-change,
  rejeição da segunda Opportunity OPEN concorrente) **foram** executados
  contra PostgreSQL real no Prompt 14 (ver seção dedicada) — a lacuna que
  resta aqui é especificamente sobre números de throughput/latência, não
  sobre corretude.

Regressão completa após F8.7: **518 passed, 15 skipped, 0 failed** (514
pré-existentes + 4 novos de `tests/test_failure_injection.py`).

## Backup, Recovery e Migrations (F8.8)

### Auditoria consolidada da cadeia de migrations

10 migrations (`0001` a `0010`), todas com `upgrade()` E `downgrade()`
implementados desde que foram escritas (F0-F7) — mas, até esta fase,
**nenhum `downgrade()` jamais havia sido executado de verdade**, em
nenhuma migration, em nenhuma sessão deste projeto. A cadeia de rollback
era uma suposição de código nunca exercitada.

`tests/test_migrations_roundtrip.py` (novo, 2 testes) corrige isso,
rodando `alembic` como subprocesso real (não em processo, para não
interferir com o banco compartilhado da suíte principal — ver docstring
do arquivo) contra um arquivo SQLite dedicado:

- **Round-trip completo**: `upgrade head` → `downgrade base` (as 10
  migrations revertidas em cadeia, pela primeira vez) → `upgrade head`
  novamente. Confirma que, após o downgrade total, só a tabela interna
  `alembic_version` resta (nenhuma tabela de domínio esquecida por um
  `downgrade()` incompleto), e que o schema final do segundo `upgrade` é
  byte-a-byte o mesmo conjunto de tabelas do primeiro.
- **Rollback parcial de um passo** (`downgrade -1`, o caso real de
  operação — reverter só a última migration aplicada, nunca o banco
  inteiro): confirma que `0010_crm_outreach` reverte isoladamente,
  removendo `outreach_messages` sem afetar `opportunities`/`activities`/
  `contacts` das migrations anteriores.

**Validação automatizada (`tests/test_migrations_roundtrip.py`): VALIDADO
REALMENTE, mas contra SQLite, não PostgreSQL** — a lógica de cada
`downgrade()` (que tabelas/colunas/índices remover, em que ordem) é a
mesma independentemente do dialeto, mas o comportamento do dialeto SQLite
para DDL (`Will assume non-transactional DDL`, visível no log do Alembic)
difere de PostgreSQL (que tem DDL transacional real); um `downgrade()` que
falhasse a meio caminho se comportaria diferente nos dois.

**Validação manual contra PostgreSQL real (Prompt 14): VALIDADO** — o
mesmo round-trip (`upgrade head` → `downgrade base` → `upgrade head`,
agora com as 13 migrations até `0013_prototype_versioning`) foi executado
manualmente via CLI do Alembic contra PostgreSQL 18 nativo nesta sessão:
as 13 migrations aplicaram, os 13 `downgrade()` reverteram em cadeia
deixando só `alembic_version`, e o `upgrade head` seguinte recriou
exatamente as mesmas 24 tabelas (comparação linha a linha, sem diferença).
Isto fecha a lacuna real (o comportamento do dialeto PostgreSQL foi
observado, não só o de SQLite) mas continua sendo uma verificação manual
desta sessão, não um teste automatizado novo — `tests/test_migrations_roundtrip.py`
em si não foi alterado para também rodar contra `REAL_POSTGRES_URL`;
escrever essa versão automatizada (mesmo padrão de `tests/infra/`) segue
como extensão natural para quando fizer sentido.

### Backup + Restore: prova de conceito real

`tests/test_backup_restore.py` (novo): cria um registro real, copia os
bytes do arquivo do banco ("backup"), apaga o arquivo original
("desastre"), e restaura a partir da cópia — confirma que o dado
recuperado é idêntico ao original. **Rótulo importante**: isto é como
backup/restore funciona de verdade em SQLite (o arquivo inteiro É o
banco); não generaliza para PostgreSQL, cujo mecanismo real seria
`pg_dump`/`pg_restore` ou WAL archiving + PITR — nenhum dos dois foi
executado nesta sessão (**NÃO VALIDADO** para Postgres, sem instância real
disponível). O valor real deste teste é provar que o CONCEITO
"backup íntegro + restore == dado recuperado" funciona de ponta a ponta
contra o SGBD que esta sessão realmente tem, não simular o procedimento de
produção.

### Política de backup para PostgreSQL em produção (convenção documentada, nunca executada)

Como nenhum PostgreSQL de produção/staging existe ainda, o que segue é uma
convenção proporcional ao tamanho deste projeto — não uma configuração já
aplicada em algum provedor, e não um SLA comercial inventado:

| Aspecto | Convenção recomendada | Por quê |
|---|---|---|
| Frequência | 1 backup lógico completo (`pg_dump`) por dia + WAL archiving contínuo, se o provedor oferecer (a maioria dos gerenciados oferece por padrão) | Um projeto deste porte não gira volume de dados que justifique mais que backup diário completo; WAL contínuo é o que reduz a janela de perda sem custo operacional adicional relevante |
| Retenção | 7 diários + 4 semanais + 3 mensais (esquema avô-pai-filho) | Convenção padrão da indústria para este porte de projeto, sem exigir armazenamento desproporcional |
| Criptografia | Em repouso, via criptografia nativa do provedor de armazenamento (a maioria oferece por padrão); nunca um backup em texto claro em um bucket público | Dado de negócio (empresas prospectadas, e-mails de contato, rascunhos de outreach) — não é dado anônimo |
| Armazenamento | Fora da instância do banco, idealmente em outra zona/região | Um backup no mesmo disco/instância do banco não sobrevive à mesma falha que o backup deveria proteger contra |
| Isolamento de acesso | Credencial de escrita de backup nunca é a mesma credencial da aplicação; a aplicação nunca tem permissão de exclusão sobre o armazenamento de backup | Um comprometimento da aplicação (ex.: RCE, credencial vazada) não deveria conseguir apagar os próprios backups |

**Nada disto foi provisionado ou testado contra um provedor real nesta
sessão** — é a convenção que qualquer provisionamento futuro de
PostgreSQL real deveria seguir, análoga à tabela de separação Local/
Staging/Production já documentada na F8.4.

### RPO / RTO (estimativas técnicas, não SLA comercial)

- **RPO (Recovery Point Objective) ≈ 24 horas** com a política acima
  (backup diário completo, sem WAL archiving garantido em todo provedor).
  Se WAL archiving contínuo estiver disponível, o RPO real cai para
  minutos — mas isso depende do provedor escolhido no dia do
  provisionamento real, não pode ser prometido genericamente aqui.
- **RTO (Recovery Time Objective)**: **NÃO VALIDADO com dado em escala de
  produção** — nunca houve um PostgreSQL real para medir o tempo de um
  `pg_restore` de verdade. O que existe como referência real e medida
  nesta sessão é o tempo de um ciclo de migração completo contra SQLite
  (schema vazio, sem volume de dados): os dois testes de
  `test_migrations_roundtrip.py` — três invocações de `alembic` cada, via
  subprocesso — completam em **≈ 2 a 6 segundos** nesta máquina. Isto NÃO
  é uma estimativa de RTO de produção (é só o tempo de recriar o SCHEMA,
  sem nenhum dado); um RTO real dependeria do volume de dados real no
  momento do incidente e só pode ser medido com um `pg_restore` real
  contra um dump de tamanho comparável ao de produção — não simulável
  honestamente sem essa infraestrutura.

### Regressão

**521 passed, 15 skipped, 0 failed** (518 pré-existentes + 2 novos de
`test_migrations_roundtrip.py` + 1 novo de `test_backup_restore.py`).

## Hardening de Produção + Auditoria de Segurança Final (F8.9)

### Vulnerabilidades de dependências (achado real desta fase)

`pip-audit` (novo, dev-only, `requirements-dev.txt`) rodado pela primeira
vez neste projeto contra `requirements.txt`: encontrou **12 avisos reais**
(via OSV/GHSA), todos em **PyJWT 2.10.1** — nenhum em nenhuma outra
dependência de produção. Cada um foi analisado individualmente contra o
uso real deste projeto (`app/domains/auth/security.py`: sempre
`jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])`,
HS256 com um único segredo simétrico, nunca `PyJWK`/`PyJWKClient`, nunca
payload destacado/`b64=false`), não apenas lido do título do CVE:

| CVE | O que é | Explorável neste projeto? |
|---|---|---|
| CVE-2026-32597 (bypass de header `crit`) | Aceita token com extensão `crit` desconhecida | **Não** — confirmado empiricamente (script de PoC executado nesta sessão): só é alcançável por quem já sabe forjar uma assinatura HMAC válida, ou seja, já precisa do `JWT_SECRET_KEY` — nesse ponto já pode forjar qualquer claim de qualquer forma |
| CVE-2025-45768 (chave "fraca", disputado pelo fornecedor) | Tamanho de chave é escolha da aplicação, não da lib | Endereçado de qualquer forma (ver abaixo) — a checagem de tamanho mínimo em produção não existia |
| CVE-2026-48526/48523 (confusão de algoritmo via `PyJWK`) | Requer `PyJWK`/mistura de algoritmos simétrico+assimétrico | **Não** — nunca usado |
| CVE-2026-48522/48524 (SSRF/DoS via `PyJWKClient`) | Requer `PyJWKClient` buscando JWKS remoto | **Não** — nunca usado (não há verificação de token de terceiros) |
| CVE-2026-48525 (DoS via payload destacado `b64=false`) | Decodifica um segmento grande antes de rejeitar | **Testado empiricamente nesta sessão** contra a chamada real do projeto (sem `detached_payload`): rejeita em `DecodeError` imediato, sem o custo amplificado descrito no CVE (2,26ms para 1MB de payload, não segundos) |

**Ação tomada mesmo assim**: `PyJWT` atualizado de `2.10.1` para `2.13.0`
(zero vulnerabilidades conhecidas após o upgrade, confirmado por
`pip-audit`) — nenhuma das CVEs era explorável no uso específico deste
projeto, mas a atualização é de baixo risco (suíte completa re-executada
sem nenhuma regressão) e elimina o ruído de auditoria/risco futuro caso o
padrão de uso mude. `pip-audit -r requirements.txt` adicionado ao CI
(`.github/workflows/ci.yml`, novo step no job `backend`) como equivalente
do `npm audit --audit-level=critical` já existente para o frontend desde
F8.1 — nunca observado rodando de verdade (nenhum push foi feito), mas
validado manualmente com sucesso nesta sessão.

**Achado adicional, descoberto pelo próprio upgrade**: PyJWT 2.13.0 passou
a emitir `InsecureKeyLengthWarning` para qualquer chave HMAC abaixo de 32
bytes (RFC 7518 §3.2) — rodar a suíte após o upgrade revelou isso na
prática, não por leitura de changelog. `_validate_production_config`
(`app/main.py`, Fase 8.3) só rejeitava o valor padrão literal, não
qualquer segredo curto — um `JWT_SECRET_KEY` de 10 caracteres não-default
passava pelo fail-fast em produção. Corrigido: agora também rejeita
qualquer `JWT_SECRET_KEY` com menos de 32 bytes em produção, com um teste
novo (`test_production_with_a_short_secret_below_32_bytes_fails_fast`).

`npm audit` (frontend): **0 vulnerabilidades**, em qualquer nível de
severidade — reconfirmado nesta fase, sem mudanças necessárias.

### Re-verificação do checklist OWASP (contra o estado pós-F8.1-F8.8)

Não repetido do zero — cada item foi checado especificamente contra o que
mudou nas fases F8.1-F8.8, já que a auditoria original (F7.5/F8.0) e o
hardening (F8.3) continuam sendo a referência de linha de base:

| Item | Estado após F8 |
|---|---|
| IDOR | Nenhum endpoint novo em F8 toca recurso pertencente a usuário — `/metrics` e `/health*` são infraestrutura pública, sem dado de negócio. Cobertura extensiva de IDOR de F7.5 permanece válida, sem mudança de superfície. |
| Mass assignment | Sem mudança — schemas Pydantic explícitos continuam sendo a única forma de entrada em toda rota. |
| Escalação de privilégio | Sem mudança — modelo de usuário permanece flat (sem papéis/permissões), nenhuma rota de F8 introduz um conceito novo de autorização. |
| SQL Injection | Sem mudança em código de produção — a única interpolação de string em SQL bruto do projeto inteiro é em `tests/infra/test_real_postgres.py` (F8.1), em um nome de tabela gerado internamente por `uuid4()`, nunca por entrada de usuário, nunca exposto por nenhuma rota. |
| XSS | Sem mudança — backend é API JSON pura; nenhuma alteração de frontend nesta fase além de headers (`next.config.ts`, F8.3). |
| CSRF | Sem mudança — arquitetura Bearer-token-via-servidor-Next.js permanece estruturalmente imune, reavaliada em F8.3. |
| SSRF | Sem mudança — nenhuma rota nova de F8 busca uma URL fornecida por request; a superfície existente (Discovery/Digital Audit, F1/F3) não foi tocada. |
| Prompt injection / segurança de IA | Ver seção dedicada abaixo. |
| CORS | Sem mudança desde o fail-fast de F8.3. |
| Headers de segurança | Sem mudança desde F8.3; testado em `test_security_hardening.py`. |
| Cookies | Sem mudança desde a revisão de F8.3. |
| Rate limiting | Re-verificado sob carga real de concorrência em F8.7 (`local_fallback` thread-safe sob 20 threads reais), não só em teste sequencial. |
| Segredos | `.env.example` nunca contém valor real; `ANTHROPIC_API_KEY` nunca logado (`tests/infra/test_real_anthropic.py` verifica isso explicitamente); `JWT_SECRET_KEY` ganhou a checagem de tamanho mínimo nesta fase (ver acima). |
| Vulnerabilidades de dependência | Ver seção acima — achado real, corrigido. |
| Vazamento de erro | Re-verificado especificamente em F8.7 (`test_failure_injection.py`): uma falha de banco no meio de uma rota de negócio comum devolve 500 limpo, sem tipo/mensagem de exceção real. |
| Limite de requisição | Sem mudança desde F8.3; `RequestSizeLimitMiddleware` continua ativo. |
| Upload de arquivo | Não aplicável — o projeto não tem nenhum endpoint de upload, em nenhuma fase. |

### Segurança de IA re-verificada (Assisted Outreach continua Level 1)

Confirmado por leitura de código (`app/domains/outreach/`,
`app/domains/briefing/`) que nenhuma mudança de F8.1-F8.8 tocou a
construção de prompt, a lógica de grounding (só contatos verificados, só
evidência já coletada) ou a validação de saída de nenhum dos dois
domínios de IA — as únicas mudanças foram observabilidade (métricas de
`ai_requests_total`/`ai_tokens_total`, F8.6) e rate limiting (F8.3), nunca
o conteúdo gerado ou o que é aceito como entrada.

**Confirmado explicitamente que nenhum mecanismo de envio automático foi
introduzido**: busca por bibliotecas de envio (`smtplib`, SDKs de
email/WhatsApp/SMS) em `app/domains/outreach` e `app/domains/briefing`
não encontra nenhuma — o único uso da palavra "whatsapp" no código é um
valor de enum (`OutreachChannel.WHATSAPP`, Fase 7) que rotula o
**canal que o humano escolherá para enviar manualmente**, nunca uma
integração de envio automatizado. "Assisted Outreach Level 1" continua
sendo exatamente isso: o sistema gera um rascunho, o humano decide se e
como enviar.

### Regressão final da F8.9

**522 passed, 15 skipped, 0 failed** (521 pré-existentes + 1 novo teste
de validação de tamanho de segredo).

## Prompt 10 — Prototype↔Company, Riscos Abertos da Fase 8, Cobertura

Fase intermediária entre a Fase 8 (produção) e a Fase 9 (geração de
protótipo por IA) — fecha um gap estrutural real e revalida os riscos que
o próprio relatório final da Fase 8 já tinha identificado como abertos.

### Prototype↔Company (achado da auditoria, seção 1)

`Prototype` não tinha nenhuma referência a `Company` — impossível saber
para qual empresa um protótipo foi feito, bloqueador direto para a Fase 9
(que precisa desse contexto). `company_id` (FK real, `NULL`-ável só para
dado legado — nunca inventado) substitui `owner_id` (`String`, nunca
preenchido em nenhuma fase, removido). Ownership derivado de `Opportunity`
(`user_owns_any_opportunity_for_company`, o mesmo padrão de `Contact` no
CRM), nunca um `owner_id` próprio. Sempre 404, nunca 403, para "não existe"
e "existe mas não é acessível" — mesmo padrão de todo o resto do CRM.
Migration `0011_prototype_company_link` usa `batch_alter_table` (primeira
vez no projeto que uma FK é adicionada a uma tabela já existente — SQLite
não suporta `ALTER TABLE ... ADD CONSTRAINT` direto), testada de verdade
em `upgrade`/`downgrade`. Decisão completa em
`docs/adr/008-prototype-company-ownership.md`.

**Consequência conhecida, não resolvida nesta fase**: o fluxo de criação
do frontend (`NewPrototypeDialog`) não tem seletor de empresa — herdado de
um fluxo standalone da Fase 6. Criar um protótipo pelo formulário atual
retorna um erro claro explicando a limitação, em vez de falhar
silenciosamente ou quebrar o build; ver `docs/prototype-builder.md`.

### Riscos abertos da Fase 8, revalidados (seção 2)

| Risco | Ação | Onde |
|---|---|---|
| Sem CSP no backend | **Implementado**: `default-src 'none'` em toda rota da API; exceção documentada e escopada só para `/docs`/`/redoc` (Swagger UI do FastAPI, confirmado por inspeção real que precisa de `cdn.jsdelivr.net` + `unsafe-inline`) | `SecurityHeadersMiddleware`, ADR-009 |
| `JWT_SECRET_KEY` sem key-versioning | **Decisão de não implementar agora** — nenhuma política de rotação existe, nenhuma produção real, over-engineering sem o requisito que o justificasse | ADR-010 |
| Sem alerta automático de saúde | **Implementado**: `scripts/healthcheck_alert.py` (novo) consulta `/health/dependencies`, sai com código != 0 quando degradado/not_ready — nunca integra com um serviço de alerta externo, isso fica para quem agenda o script | `scripts/healthcheck_alert.py`, testado contra um servidor real (mesma metodologia de F8.7) |
| Rate limiter local não distribuído | **Decisão de não implementar um rate limiter distribuído agora** (nenhuma réplica existe) — formalizada com comentário no código + 2 testes estruturais que quebram se a limitação for silenciosamente removida no futuro | `app/core/rate_limit.py`, `tests/test_rate_limit.py`, ADR-011 |

### Auditoria de cobertura (seção 3)

`pytest-cov` (novo, dev-only) rodado por completo pela primeira vez neste
projeto: **94% de cobertura de linha no backend** (4616 statements, 273
não cobertos). Os piores pontos identificados e o que foi feito:

- **`app/domains/discovery/cache.py` (66% → corrigido)**: TODO o caminho
  de sucesso do cache (cache hit, deserialização, escrita) nunca tinha
  sido exercitado por nenhum teste — Redis está sempre indisponível nesta
  suíte, então só o caminho "Redis ausente" tinha cobertura. Corrigido com
  `tests/discovery/test_cache.py` (8 testes, via `fakeredis`).
- **`app/api/routes/outreach.py` (71% → corrigido)**: sem
  `ANTHROPIC_API_KEY` em nenhum teste, o caminho de SUCESSO de
  `generate_outreach`, e as rotas `edit`/`transition` inteiras (impossível
  até criar um Outreach para testá-las), nunca tinham sido exercitados.
  Corrigido com 11 testes novos em `tests/outreach/test_api.py`, injetando
  um provider de IA fake no ponto de resolução de `OutreachService` (mesmo
  padrão já usado em `tests/outreach/test_service.py`).
- **`enqueue_or_run_*` em `app/domains/{discovery,audit,briefing}/jobs.py`
  (59% cada → parcialmente corrigido)**: o caminho "Redis disponível →
  retorna 'queued'" nunca tinha sido exercitado (toda rota HTTP sempre cai
  no fallback síncrono). Corrigido com `tests/jobs/test_enqueue_or_run.py`
  (3 testes, `fakeredis`). O que **continua** sem cobertura de unidade,
  deliberadamente: o corpo de `run_discovery_search`/`run_digital_audit`/
  `run_sales_brief` (a função que abre sua PRÓPRIA `SessionLocal`, para
  rodar em um processo de worker separado) — testá-la diretamente exigiria
  ou vazar um commit real no SQLite compartilhado da suíte, ou um
  monkeypatch complexo o suficiente para mascarar bugs reais. A lógica que
  ela chama já é testada extensivamente pelo outro branch (`db is not
  None`, usado por toda rota HTTP); o mecanismo genérico de execução via
  RQ já é provado por `tests/jobs/test_worker_integration.py` (F8.2).
- **`app/worker.py` (56%, documentado, não testado)**: `main()` chama
  `Worker(...).work()`, que bloqueia para sempre — não testável
  diretamente sem um subprocesso com timeout, de baixo valor real: o
  mesmo `Worker`/`.work()` já é exercitado (com `burst=True`, que não
  bloqueia) em `tests/jobs/test_worker_integration.py`.

  **Correção (sessão do launcher local, depois do Prompt 15) — esta
  afirmação estava errada, não só otimista**: `test_worker_integration.py`
  usa `SimpleWorker`, não `Worker` (`from rq import Queue, SimpleWorker`,
  confirmado por leitura direta do arquivo) — a classe real que
  `app/worker.py` instancia nunca foi exercitada por NENHUM teste do
  projeto, em nenhuma fase, até este `main()` ser executado de verdade
  pela primeira vez nesta sessão seguinte. O resultado real: crashou no
  primeiro job (`os.fork()` não existe no Windows) — o "de baixo valor
  real" da avaliação original não se sustentou; era exatamente o caminho
  que faltava exercitar. Ver a seção "RQ Worker (F8.2)" acima para a
  correção aplicada (`SimpleWorker` seletivo por plataforma) e a prova ao
  vivo com uma busca de Discovery real.

**Frontend**: `@vitest/coverage-v8` (novo, dev-only) rodado por completo
pela primeira vez — 86.7% statements / 76.7% branches sobre os arquivos
exercitados pelos testes. Pior ponto real encontrado: `toolbar.tsx` (50%
statements) — nunca tinha um teste dedicado, só cobertura indireta via
`prototype-builder.test.tsx`, que nunca exercitava renomear o protótipo
nem os botões de desfazer/refazer. Corrigido com `toolbar.test.tsx` (6
testes novos). Outros pontos baixos (`prototype-builder.tsx`,
`property-panel.tsx`, `node-renderer.tsx`, `prospects-filters.tsx`) são
majoritariamente ramos condicionais de UI (não caminhos de erro de rede/
entrada malformada) — documentados aqui, não perseguidos até 100%, por
retorno decrescente frente ao objetivo desta seção ("identificar pontos
cegos reais", não cobertura total).

**Nota sobre `@vitest/coverage-v8` e `@types/node`**: instalado com
`--legacy-peer-deps` — há um conflito de peer dependency entre
`vitest@5` (exige `@types/node >=22`) e o `@types/node@^20` já fixado no
projeto. Puramente uma divergência de tipos de uma ferramenta de
desenvolvimento (não afeta o runtime nem o bundle de produção) — não
resolvido nesta fase (fora de escopo: exigiria decidir se `@types/node`
sobe de major version, uma mudança maior que uma ferramenta de cobertura
justifica sozinha).

### ADRs (seção 4)

`docs/adr/` (novo — antes do Prompt 10, ADRs só existiam como menções em
texto corrido em `docs/crm.md`, nunca em arquivos próprios): ADR-008
(Prototype↔Company), ADR-009 (CSP), ADR-010 (JWT key-versioning — decisão
de não fazer), ADR-011 (rate limiter distribuído — decisão de não fazer).
Ver `docs/adr/README.md` para o índice completo.

### Regressão final do Prompt 10

**Backend: 564 passed, 15 skipped, 0 failed** (522 pré-existentes + 42
novos/reescritos entre Prototype↔Company, CSP, rate limit, healthcheck
script, e a auditoria de cobertura). **Frontend: 169 passed, 0 failed**
(163 pré-existentes + 6 novos de `toolbar.test.tsx`); typecheck, lint (0
erros) e build permanecem verdes.
