# Arquitetura — estado real após a Fase 4

Este documento resume a arquitetura tal como **implementada** até a Fase 4.
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
  Identity Resolution   (Fase 2 — implementado: matching + DedupCandidate)
      │
      ▼
  Digital Audit          (Fase 3 — implementado: SSRF-safe fetch + sinais HTML)
      │
      ▼
  Evidence Consolidation (existe desde a Fase 0; Discovery/Audit já a usam)
      │
      ▼
  Website Quality Score  (Fase 3 — implementado, separado do Opportunity Score)
      │
      ▼
  Opportunity Scoring    (Fase 4 — implementado: determinístico, sem IA)
      │
      ▼
  Sales Brief            (Fase 4 — implementado: único componente com IA)
```

A Fase 1 implementa o primeiro estágio real do pipeline: descoberta de
candidatos por uma fonte externa. A Fase 2 decide se um candidato inédito é
uma empresa já conhecida ou uma empresa nova. A Fase 3 verifica, para uma
empresa já identificada, se ela tem um website próprio acessível e avalia
sua qualidade técnica. A Fase 4 combina os sinais das três fases
anteriores em um Opportunity Score determinístico e gera, via IA, um
briefing de prospecção estritamente fundamentado nesses dados — ver
`docs/discovery.md`, `docs/identity-resolution.md`, `docs/digital-audit.md`,
`docs/opportunity-scoring.md` e `docs/sales-brief.md` para o detalhamento
completo de cada uma.

## O que existe hoje

- API HTTP (FastAPI) com `/health`, `/health/dependencies`,
  `POST /api/discovery/search`, `GET /api/discovery/runs/{run_id}`,
  `POST /api/identity/resolve`, `POST /api/audit/{company_id}`,
  `GET /api/audit/{company_id}`, `POST /api/scoring/{company_id}`,
  `GET /api/scoring/{company_id}`, `POST /api/sales-brief/{company_id}` e
  `GET /api/sales-brief/{company_id}`.
- Schema de banco completo para as entidades estruturais da v0.2, mais os
  campos de rastreabilidade de execução de busca (Fase 1), de resolução de
  identidade (Fase 2) e de auditoria digital (Fase 3) — ver `data-model.md`.
- **Discovery funcional**: provider da Google Places API (New), com
  timeout, retry limitado, paginação, cache best-effort e rastreamento de
  custo. Ver `docs/discovery.md`.
- **Identity Resolution funcional**: matching por telefone/site oficial/
  nome/endereço/região/proximidade, com `DedupCandidate` auditando toda
  decisão e nunca fundindo automaticamente casos ambíguos. Ver
  `docs/identity-resolution.md`.
- **Digital Audit funcional**: para uma empresa com um candidato de
  website (produzido por Discovery/Identity Resolution), valida a URL
  contra SSRF, busca a página com timeout/limite de redirects/limite de
  tamanho, extrai sinais técnicos determinísticos (HTML padrão, sem
  JavaScript) e calcula um **Website Quality Score** reprodutível,
  separado do Opportunity Score. Ver `docs/digital-audit.md`.
- **Opportunity Score funcional**: combina Website Gap, Website Quality
  Gap, Digital Presence Gap, Business Visibility, Segment Fit e
  Contactability em um score 0-100 determinístico, com breakdown
  explicável por dimensão, confiança separada do score e classificação em
  5 faixas. Nenhuma IA participa. Ver `docs/opportunity-scoring.md`.
- **Sales Brief funcional**: único componente com IA de todo o sistema —
  gera um briefing de prospecção estritamente fundamentado em dados já
  coletados, com defesa contra prompt injection, validação estrutural da
  resposta e degradação graciosa quando o provider está indisponível. Ver
  `docs/sales-brief.md`.
- Camada de configuração centralizada (`app/core/config.py`), agora
  incluindo as configurações de Discovery, Identity Resolution, Digital
  Audit e Sales Brief (Anthropic).
- Logging estruturado com correlação por requisição.
- Tratamento de erro consistente (`app/core/errors.py`).
- Abstração de job (`app/jobs/`) com quatro jobs reais (`DiscoveryJob`,
  `DigitalAuditJob`, `SalesBriefJob`; Identity Resolution e Opportunity
  Score rodam de forma síncrona embutida — o primeiro na persistência do
  Discovery, o segundo porque é puramente local/determinístico e não
  chama nada externo), todos com fallback síncrono documentado quando o
  Redis está indisponível.
- Migrations Alembic geradas a partir dos modelos, com cinco migrations
  aplicadas e testadas (schema inicial; execução de busca; resolução de
  identidade; auditoria digital e Website Quality Score; Opportunity
  Score e Sales Brief).

## O que não existe ainda

- Fusão de duas `Company` já existentes exposta por HTTP (existe e é
  testada só na camada de serviço — falta autenticação no sistema).
- Consumo da fila de revisão humana de Identity Resolution
  (`DedupCandidate.status=pending_review`) — trabalho de fase futura.
- Qualquer agente de IA multi-etapa ou framework de agentes (CrewAI,
  AutoGen, LangChain, LangGraph) — o Sales Brief é uma única chamada
  request/response a um provider de texto, não um agente.
- Uma chamada real à API da Anthropic (sem `ANTHROPIC_API_KEY` disponível
  neste ambiente de desenvolvimento — ver `docs/sales-brief.md`).
- Providers de Discovery além do Google Places.
- PostGIS (distância geográfica calculada em Python, tanto na Fase 2
  quanto na Fase 3).
- Proteção completa contra DNS rebinding via IP pinning no Digital Audit
  (a validação de SSRF por resolução prévia existe; fixar a conexão TCP ao
  IP validado não — ver `docs/digital-audit.md`, seção "Segurança").
- Crawling: o Digital Audit analisa só a página inicial do candidato.
- Dashboard/frontend, Prototype Builder, CRM.

## Stack

| Camada | Escolha | Estado |
|---|---|---|
| Backend | Python 3.12+ / FastAPI | Implementado |
| ORM / schema | SQLAlchemy 2.0 + Alembic | Implementado |
| Banco | PostgreSQL 16 (produção/Docker) | Config pronta, não validada nesta máquina (sem Docker) |
| Fila | Redis + RQ | Conexão pronta; jobs implementados, com fallback síncrono quando o Redis está indisponível |
| Cliente HTTP externo | httpx (timeout + retry manual) | Implementado (Discovery e Digital Audit) |
| Normalização de telefone | `phonenumbers` | Implementado |
| Similaridade de texto (matching) | `RapidFuzz` | Implementado |
| Extração de HTML | `html.parser` (biblioteca padrão) | Implementado — nenhuma dependência nova na Fase 3 |
| Validação de SSRF | `ipaddress`/`socket` (biblioteca padrão) | Implementado |
| Logging | structlog | Implementado |
| Camada de raciocínio (LLM) | Claude API (Anthropic Messages API, via `httpx` puro) | Implementado — só no Sales Brief; sem chave real neste ambiente |
| Frontend | Next.js (planejado) | Não iniciado |

## Desvio documentado: `WebsiteQuality` mora no domínio `audit`

A arquitetura v0.2 trata Website Quality Score como um conceito distinto do
Opportunity Score. Isso permanece verdadeiro na modelagem — e agora
também na implementação: `app/domains/audit/scoring.py` calcula um score
que nunca representa "chance de venda" ou "prioridade comercial", só
qualidade técnica/presença do website. O prompt de implementação da
Fase 0 não listava um domínio `quality` separado na árvore de diretórios
esperada — apenas `discovery/identity/audit/evidence/scoring/briefing`.
Como `WebsiteQuality` é um subproduto 1:1 de uma execução de auditoria,
sua tabela vive em `app/domains/audit/models.py`, junto de
`AuditSnapshot`. `OpportunityScore` permanece em `app/domains/scoring/`.
Decisão de organização de arquivos, não uma mudança de conceito
arquitetural — ver `data-model.md`.

## Decisão da Fase 1 (reafirmada na Fase 3): execução síncrona como fallback do Redis

A arquitetura v0.2 prevê processamento assíncrono via fila (Redis + RQ). O
Digital Audit (`app/domains/audit/jobs.py`) segue exatamente o mesmo
padrão já estabelecido pelo Discovery na Fase 1: `enqueue_or_run_audit()`
executa de forma síncrona quando a fila está inacessível (o caso desta
máquina de desenvolvimento, que não tem Redis instalado), em vez de falhar
a requisição. Redis/RQ continuam sendo a arquitetura oficial — não
removidos, não substituídos. Ver `docs/discovery.md` e
`docs/digital-audit.md`.

## Refatorações da Fase 3 (sem mudança de comportamento para Fases 1/2)

- `is_trusted_website`/`UNTRUSTED_WEBSITE_DOMAINS`, que viviam só em
  `app.domains.identity.matching` (Fase 2), foram promovidos para
  `app.domains.discovery.normalization` — módulo do qual `identity` já
  dependia para outras normalizações, e do qual `audit` também passou a
  depender. `identity.matching` reexporta do novo local para não quebrar
  código existente. Suíte de testes da Fase 2 revalidada sem alterações.
- `app.domains.evidence.queries` ganhou `upsert_evidence`, uma versão
  generalizada do padrão append-only que `discovery.persistence.
  _upsert_evidence` já implementava desde a Fase 1 (aceita `state` e
  `audit_snapshot_id` variáveis, que o Digital Audit precisa e o Discovery
  não). O `_upsert_evidence` original do Discovery não foi tocado — zero
  risco de regressão na Fase 1.

## Refatorações da Fase 4 (sem mudança de comportamento para Fases 0-3)

- `OpportunityTier` (placeholder da Fase 0, nunca persistido com um valor
  real até aqui) ganhou 2 valores novos (`medium_high`, `very_low`) — de 3
  para 5 faixas. Como nenhuma linha de `opportunity_scores` tinha `tier`
  preenchido antes da Fase 4, não houve dado histórico para migrar.
- `OpportunityScore` ganhou `confidence`, `scoring_version` e `updated_at`
  — aditivo, sem remover nenhum campo existente.

## Próxima fase

**Fase 5 — Dashboard.** Interface para visualizar empresas descobertas,
scores e briefings gerados, e para disparar manualmente auditoria/score/
briefing. Não inicia automaticamente — aguarda aprovação explícita.
