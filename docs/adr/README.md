# Architecture Decision Records

O projeto usa ADRs desde a auditoria da Fase 7.0, mas até o Prompt 10 elas
só existiam como menções em texto corrido dentro de `docs/crm.md`
(`ADR-001`, `ADR-003` a `ADR-007` — `ADR-002` nunca foi usado em nenhum
documento; não foi reconstruído aqui, permanece um número não atribuído).
Esta pasta padroniza o formato para toda decisão de arquitetura **a partir
do Prompt 10** — as ADRs anteriores continuam vivendo como estão, em
`docs/crm.md`, e não foram retroativamente extraídas para arquivos
próprios (fora do escopo do Prompt 10, que pediu ADRs para as decisões
desta fase, não uma migração das anteriores).

## Índice

| ADR | Título | Status |
|---|---|---|
| [008](./008-prototype-company-ownership.md) | Ownership de Prototype derivado de Opportunity, não um `owner_id` próprio | Aceita |
| [009](./009-backend-content-security-policy.md) | Content-Security-Policy restritiva no backend, com exceção só para `/docs`/`/redoc` | Aceita |
| [010](./010-jwt-key-versioning.md) | Não implementar rotação de `JWT_SECRET_KEY` com múltiplas chaves (`kid`) agora | Aceita (reconsiderar sob gatilho) |
| [011](./011-rate-limiter-distribuido.md) | Não implementar rate limiter distribuído agora | Aceita (reconsiderar sob gatilho) |
| [012](./012-no-prototype-version-yet.md) | Não criar `PrototypeVersion` nesta fase (Prompt 11) | Aceita (reconsiderar sob gatilho) |

## Formato

Cada ADR é curta: Contexto, Decisão, Consequências, e (quando a decisão é
"não fazer agora") um gatilho explícito de quando reconsiderar — para que
a decisão não fique perdida em uma mensagem de commit ou seja esquecida
até alguém redescobrir o mesmo problema do zero.
