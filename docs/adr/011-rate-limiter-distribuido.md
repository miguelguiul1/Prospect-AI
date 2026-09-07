# ADR-011: Não implementar rate limiter distribuído agora

**Status**: Aceita — decisão de NÃO implementar, com gatilho de reconsideração (Prompt 10, seção 2.4)

## Contexto

`app.core.rate_limit` usa Redis como contador primário (compartilhado
entre qualquer número de réplicas, já que é um serviço externo) — esse
caminho já é "distribuído" por natureza. O problema é o **fallback**: para
login/registro (`on_unavailable="local_fallback"`, Fase 8.3), quando Redis
está inacessível, cada processo do backend usa um `dict` Python em memória
como segunda linha de defesa. Com uma única réplica, isso funciona bem.
Com múltiplas réplicas atrás de um load balancer, cada réplica tem seu
próprio `dict` — um atacante distribuído entre réplicas efetivamente
multiplica o limite real por N réplicas.

O relatório final da Fase 8 listou isto como um risco aceito para
instância única, nunca formalizado além de um comentário no código.

## Decisão

**Não implementar um rate limiter distribuído de propósito geral agora**
(ex.: um algoritmo de token bucket coordenado via Lua script no Redis, ou
um serviço dedicado). Motivos:

1. **Nenhuma réplica existe hoje.** O projeto roda como uma única
   instância de backend (`docker-compose.yml`: um serviço `backend`, sem
   réplicas). O risco só se materializa no dia em que uma segunda réplica
   for adicionada — implementar a solução antes do problema existir é
   over-engineering.
2. **O caminho primário já é distribuído.** Quando Redis está disponível
   (o caso comum, inclusive em produção com Redis gerenciado), o contador
   via `INCR`/`EXPIRE` já coordena corretamente entre qualquer número de
   réplicas — só o fallback (Redis indisponível) tem esta limitação, e o
   fallback é precisamente o caminho degradado, não o caminho principal.
3. Uma solução distribuída de verdade para o caso degradado (Redis já
   fora do ar) exigiria OUTRO armazenamento compartilhado independente de
   Redis — adicionar uma segunda peça de infraestrutura só para cobrir o
   fallback do rate limiter seria desproporcional ao risco.

## O que foi feito nesta fase (não implementação, formalização)

- Comentário explícito em `app/core/rate_limit.py`, junto à declaração do
  `dict` de fallback, apontando exatamente esta limitação e apontando para
  esta ADR.
- `tests/test_rate_limit.py` (novo, 2 testes): prova estruturalmente que o
  estado é um `dict` Python comum (não Redis, não nada distribuído) e que
  duas "réplicas" simuladas (dois resets independentes do mesmo estado)
  nunca coordenam um limite combinado — para que uma refatoração futura
  que trocasse essa estrutura por algo distribuído sem revisar esta ADR
  quebre um teste, em vez de silenciosamente divergir da documentação.

## Quando reconsiderar

- No momento em que uma segunda réplica do backend for adicionada (scaling
  horizontal real) — a essa altura, o fallback local deixa de ser uma
  degradação aceitável e passa a ser uma lacuna de segurança ativa (limite
  efetivo = `max_attempts` × número de réplicas, durante qualquer
  indisponibilidade de Redis).
- Nesse momento, a extensão mais simples é usar o próprio Redis para o
  fallback também (ex.: um Redis secundário/réplica só para rate
  limiting) — não necessariamente um sistema novo.

## Consequências

- Nenhuma mudança de comportamento nesta fase — o fallback local continua
  exatamente como era, agora com a limitação documentada em três lugares
  (código, ADR, `docs/production-readiness.md`) em vez de um.
