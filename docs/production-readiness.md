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

**Importante sobre validação:** o arquivo YAML foi validado
estruturalmente (`yaml.safe_load`, parse sem erro, jobs/steps presentes
como esperado) e todo comando referenciado já foi executado manualmente
com sucesso nesta mesma sessão. A execução real do workflow em si — o
GitHub Actions de fato rodando os containers de serviço e reportando
verde — **nunca foi observada**, porque nenhum push foi feito durante a
Fase 8 (regra explícita desta fase). Isso só será confirmado depois que o
usuário decidir publicar.

### `tests/infra/` — testes contra infraestrutura real

Dois arquivos novos, com uma regra em comum: cada um usa sua própria
variável de ambiente (`REAL_POSTGRES_URL`/`REAL_REDIS_URL`), independente
do `DATABASE_URL`/`REDIS_URL` que o resto da suíte já fixa como SQLite/porta
morta antes de qualquer import (ver `tests/conftest.py`). Se a infraestrutura
real não responder, a suíte inteira do arquivo é pulada com um motivo
explícito — nunca falha silenciosamente, nunca finge sucesso.

Em desenvolvimento local (sem PostgreSQL/Redis reais, mesma limitação
documentada desde a Fase 0): as 11 verificações destes dois arquivos
aparecem como `skipped`, nunca como `passed`. Em CI, com os serviços reais
do workflow acima, elas executam de verdade.

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
- Execução real do worker contra Redis real: **NÃO VALIDADO** — sem Redis
  disponível nesta máquina. O workflow de CI (F8.1) provisiona Redis real
  como serviço, mas ainda não inclui uma etapa que suba `app.worker` e
  enfileire um job real de ponta a ponta — isso é uma extensão natural e
  pequena para quando o workflow for observado rodando pela primeira vez,
  não implementada agora para não expandir escopo sem necessidade.

## Rate Limiting endurecido + Security Hardening (F8.3)

**Política de Redis indisponível diferenciada por criticidade** (antes: uma
única política "fail-open" para tudo, achado confirmado ao vivo na
auditoria F7.5/F8.0). `app.core.rate_limit.check_and_increment` ganhou um
parâmetro `on_unavailable`:

| Operação | Política | Por quê |
|---|---|---|
| Login | `local_fallback` | Negar login por completo por uma dependência opcional fora do ar seria pior que o risco mitigado — usa um contador local em memória do processo como segunda linha de defesa, **nunca equivalente a um limite distribuído real** (não coordena entre réplicas, é perdido a cada restart). |
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

Estado real de cada dependência externa, nesta sessão — nunca simulado
como validado quando não foi:

| Dependência | Status | Evidência |
|---|---|---|
| PostgreSQL | **NOT VALIDATED (ao vivo)** / VALIDADO EM CI (estrutural, nunca observado rodar) | `tests/infra/test_real_postgres.py` (7 testes: conectividade, versão, todas as tabelas F0-F7, índice parcial real, race condition de stage-change, concorrência de criação de Opportunity) — escrito e pronto, roda de verdade em CI contra um serviço `postgres:16-alpine` real; nunca observado executando nesta sessão (nenhum push foi feito) |
| Redis | **NOT VALIDATED (ao vivo)** / VALIDADO EM CI (estrutural) | `tests/infra/test_real_redis.py` (5 testes: rate limiter real) + `tests/infra/test_real_worker.py` (novo nesta fase: worker RQ contra Redis real, não `fakeredis`) — mesma situação: pronto, nunca observado rodando |
| RQ (worker) | **VALIDADO COM MOCK** (fakeredis, F8.2) + estrutural em CI (não observado) | `tests/jobs/test_worker_integration.py` |
| Anthropic | **NOT VALIDATED — credencial ausente** | `tests/infra/test_real_anthropic.py` (novo): pula automaticamente sem `ANTHROPIC_API_KEY`; se uma chave real for adicionada como GitHub Secret, faz UMA chamada mínima real (poucas dezenas de tokens) para provar conectividade/autenticação — nunca geração em lote. Nenhuma chave foi fornecida em nenhuma fase deste projeto (F0-F8) |
| PostgreSQL — concorrência (Opportunity, stage-change) | Código escrito e correto (revisão + teste pronto para CI), **nunca executado contra Postgres real nesta sessão** | Mesmo arquivo acima |
| Redis — restart/reconexão sob operação | **NOT VALIDATED** | Exigiria controlar o ciclo de vida de um processo Redis real (matar/reiniciar), não só verificar presença/ausência — fora do alcance de um teste automatizado sem infraestrutura orquestrável de verdade |

**Resumo honesto**: nenhuma das quatro dependências externas (PostgreSQL,
Redis, RQ contra Redis real, Anthropic) foi observada funcionando de
verdade nesta sessão — porque nenhuma delas esteve disponível. O que a
Fase 8 entrega é a **capacidade de validação real**, pronta e testada
estruturalmente, que só precisa da infraestrutura existir (e do workflow
de CI ser observado rodando, o que exige um push) para deixar de ser
"NOT VALIDATED" e virar "REAL" de verdade — sem reescrever nada quando
esse dia chegar.

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
- Qualquer teste de carga contra PostgreSQL/Redis reais — os números desta
  seção são todos contra SQLite; `tests/infra/` (F8.1) contém os testes de
  concorrência prontos para PostgreSQL real, mas continuam nunca
  executados nesta sessão (exigem infraestrutura ausente).

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

**Validação: VALIDADO REALMENTE, mas contra SQLite, não PostgreSQL** — a
lógica de cada `downgrade()` (que tabelas/colunas/índices remover, em que
ordem) é a mesma independentemente do dialeto, mas o comportamento do
dialeto SQLite para DDL (`Will assume non-transactional DDL`, visível no
log do Alembic) difere de PostgreSQL (que tem DDL transacional real); um
`downgrade()` que falhasse a meio caminho se comportaria diferente nos
dois. Rodar esta mesma suíte contra PostgreSQL real (via
`REAL_POSTGRES_URL`, mesmo padrão de `tests/infra/`) é a extensão natural
quando essa infraestrutura existir — não implementada agora para não medir
uma coisa e reportar como se fosse outra.

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
