# Arquitetura — estado real após a Fase 1

Este documento resume a arquitetura tal como **implementada** até a Fase 1.
Ele não substitui a análise completa de arquitetura (v0.2), que continua
sendo a referência de decisão para as fases futuras — este arquivo existe
para não deixar a documentação divergir do código à medida que ele avança.

## Visão geral

Prospect AI é um monólito modular em Python (FastAPI), organizado por
domínio de negócio dentro do mesmo backend — não por microsserviço.

```
Região + segmento
      │
      ▼
  Discovery             (Fase 1 — implementado: provider Google Places)
      │
      ▼
  Identity Resolution   (Fase 2 — não implementado; estrutura de dados existe)
      │
      ▼
  Digital Audit         (Fase 3 — não implementado; estrutura de dados existe)
      │
      ▼
  Evidence Consolidation (estrutura de dados existe desde a Fase 0; Discovery já a usa)
      │
      ▼
  Opportunity Scoring    (Fase 4 — não implementado; estrutura de dados existe)
      │
      ▼
  Sales Brief            (Fase 4 — não implementado)
```

A Fase 1 implementa o primeiro estágio real do pipeline: descoberta de
candidatos por uma fonte externa, normalização e persistência rastreável.
Ela **não** decide identidade definitiva entre registros de fontes
diferentes (Fase 2) nem avalia presença digital ou oportunidade (Fases 3
e 4) — ver `docs/discovery.md` para o detalhamento completo.

## O que existe hoje

- API HTTP (FastAPI) com `/health`, `/health/dependencies`,
  `POST /api/discovery/search` e `GET /api/discovery/runs/{run_id}`.
- Schema de banco completo para as entidades estruturais da v0.2, mais os
  campos de rastreabilidade de execução de busca introduzidos na Fase 1
  (ver `data-model.md`).
- **Discovery funcional**: provider da Google Places API (New) (Text
  Search e Nearby Search), com timeout, retry limitado com backoff, rate
  limit tratado, paginação, cache best-effort e rastreamento de custo por
  chamada. Ver `docs/discovery.md`.
- Camada de configuração centralizada (`app/core/config.py`), lendo
  exclusivamente de variáveis de ambiente — agora incluindo as
  configurações de Discovery.
- Logging estruturado com correlação por requisição
  (`app/core/logging.py`, `app/core/middleware.py`).
- Tratamento de erro consistente (`app/core/errors.py`).
- Abstração de job (`app/jobs/`) agora com um job real (`DiscoveryJob`),
  com fallback síncrono documentado quando o Redis está indisponível.
- Migrations Alembic geradas a partir dos modelos, com duas migrations
  aplicadas e testadas (schema inicial + detalhes de execução de busca).

## O que não existe ainda

- Identity Resolution: nenhuma fusão automática entre `CompanySource` de
  fontes diferentes, nenhuma fila `DedupCandidate` (ainda não criada —
  ver `data-model.md`).
- Qualquer checagem real de presença digital (site, redes sociais) além
  do que a própria Google Places já retorna como campo estruturado.
- Qualquer cálculo de Website Quality Score ou Opportunity Score.
- Qualquer agente de IA (nenhuma chamada à API da Anthropic é feita — o
  próprio Discovery é inteiramente determinístico, sem síntese textual).
- Providers além do Google Places (OpenStreetMap fica documentado como
  extensão futura — ver `docs/discovery.md`).
- Dashboard/frontend.
- Prototype Builder e CRM.

## Stack

| Camada | Escolha | Estado |
|---|---|---|
| Backend | Python 3.12+ / FastAPI | Implementado |
| ORM / schema | SQLAlchemy 2.0 + Alembic | Implementado |
| Banco | PostgreSQL 16 (produção/Docker) | Config pronta, não validada nesta máquina (sem Docker) |
| Fila | Redis + RQ | Conexão pronta; `DiscoveryJob` implementado, com fallback síncrono quando o Redis está indisponível |
| Cliente HTTP externo | httpx (timeout + retry manual) | Implementado (`GooglePlacesProvider`) |
| Normalização de telefone | `phonenumbers` | Implementado |
| Logging | structlog | Implementado |
| Camada de raciocínio (LLM) | Claude API | Não integrada — reservada nas configs |
| Frontend | Next.js (planejado) | Não iniciado |

## Desvio documentado: `WebsiteQuality` mora no domínio `audit`

A arquitetura v0.2 trata Website Quality Score como um conceito distinto do
Opportunity Score. Isso permanece verdadeiro na modelagem. O prompt de
implementação da Fase 0, porém, não lista um domínio `quality` separado na
árvore de diretórios esperada — apenas `discovery/identity/audit/evidence/
scoring/briefing`. Como `WebsiteQuality` é um subproduto 1:1 de uma execução
de auditoria, sua tabela foi colocada em `app/domains/audit/models.py`,
junto de `AuditSnapshot`, em vez de criar um domínio novo só para uma
tabela. `OpportunityScore` permanece em `app/domains/scoring/`. É uma
decisão de organização de arquivos, não uma mudança de conceito
arquitetural — ver `data-model.md`.

## Decisão da Fase 1: execução síncrona como fallback do Redis

A arquitetura v0.2 prevê processamento assíncrono via fila (Redis + RQ). A
Fase 1 mantém essa abstração intacta (`app/jobs/base.py`,
`app/domains/discovery/jobs.py`), mas — como esta máquina de
desenvolvimento não tem Redis instalado (mesma limitação documentada desde
a Fase 0) — `enqueue_or_run_discovery()` executa a busca de forma síncrona
quando a fila está inacessível, em vez de falhar a requisição. Isso é um
modo operacional, não uma substituição do Redis: em produção, com Redis
disponível, o caminho enfileirado é sempre o usado. Ver `docs/discovery.md`,
seção "Jobs e execução assíncrona", para o detalhamento e a justificativa
de por que isso não é o mesmo problema arquitetural que "trocar Redis por
SQLite" (que a Fase 0 já havia recusado a fazer).

## Próxima fase

**Fase 2 — Identity Resolution + deduplicação.** Implementar as regras de
correspondência entre `CompanySource` (sinais fortes/médios/fracos,
conforme a arquitetura v0.2, seção 13) e a fila de revisão humana
(`DedupCandidate`, ainda não criada). Não inicia automaticamente — aguarda
aprovação explícita.
