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
