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
