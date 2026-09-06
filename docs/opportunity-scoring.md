# Opportunity Score — Fase 4

## O que este score É e o que NÃO é

O Opportunity Score é uma **heurística de priorização comercial**: um
número de 0 a 100 que ajuda a decidir em que ordem abordar prospects já
descobertos (Fase 1) e identificados (Fase 2), combinando sinais públicos
já coletados pela Digital Audit/Evidence Layer (Fase 3).

Ele **NÃO é**:

- Uma probabilidade estatística de conversão (não foi calibrado contra
  nenhum dado real de vendas — ver "Limitações" abaixo).
- Uma estimativa de faturamento, orçamento ou capacidade de compra do
  prospect.
- O Website Quality Score (Fase 3). Aquele mede só a qualidade técnica de
  UM website; este combina o Website Quality Score com outros sinais para
  estimar prioridade de venda. Os dois são calculados, persistidos e
  documentados separadamente — nunca confundidos (ver
  `tests/scoring/test_scoring.py::TestCasosImportantes::
  test_opportunity_score_is_never_a_copy_of_website_quality_score`).

Nenhuma IA participa deste cálculo. `app.domains.scoring.scoring.
compute_opportunity_score` é uma função pura — os mesmos dados de entrada
sempre produzem o mesmo resultado.

## Dimensões, pesos e por quê

| Dimensão | Peso | Fonte do sinal | Por quê esse peso |
|---|---|---|---|
| Website Gap | 25% | `AuditSnapshot.site_state` (Fase 3) | A ausência (ou inacessibilidade) de um site próprio é o sinal mais direto de que a agência tem algo a vender. |
| Website Quality Gap | 20% | `WebsiteQuality.score` (Fase 3), invertido | Um site que existe mas é tecnicamente ruim também é oportunidade — só que menor que "não ter site nenhum". |
| Digital Presence Gap | 15% | `Evidence(field="website")` bruto, comparado contra `UNTRUSTED_WEBSITE_DOMAINS` | Presença em rede social/agregador sem domínio próprio é um gancho comercial claro. Peso moderado porque a Fase 1-3 não têm um provider dedicado de redes sociais — o único sinal disponível é se o valor de "website" coletado pelo Discovery aponta para um domínio social/agregador. |
| Business Visibility | 15% | `Evidence(field="rating"/"review_count")` (Fase 1) | Indício de que o negócio é real/ativo/encontrável — NUNCA um proxy de faturamento (ver seção dedicada abaixo). Peso deliberadamente moderado para não deixar esse sinal dominar. |
| Segment Fit | 15% | `Company.category.slug` (Fase 0/1) | Categorias historicamente mais responsivas a serviços de site/marketing digital recebem uma leve vantagem. Tabela pequena e explícita (`SEGMENT_FIT_SCORES`), não uma nova taxonomia. |
| Contactability | 10% | `Evidence(field="phone"/"address"/"website_contact_available")` | Menor peso de propósito: descreve se é FÁCIL abordar o prospect, não se vale a pena abordá-lo. |

Os pesos somam exatamente 1.0 quando as 6 dimensões têm dado disponível —
ver `app.domains.scoring.scoring.WEIGHTS`.

## Por que uma dimensão sem dado é EXCLUÍDA, não vira 0 ou 100

Este é o princípio mais importante da fórmula, e a extensão direta do
Evidence Layer (Fase 0: "ausência de evidência nunca é evidência de
ausência") para o scoring: quando uma dimensão não tem dado suficiente
(ex.: nenhuma avaliação coletada, empresa sem categoria), ela é **excluída**
do cálculo — nunca recebe um valor assumido (nem 0 "pessimista", nem 100
"otimista"). Os pesos das dimensões restantes são renormalizados para somar
1.0 entre si. Isso significa que o Opportunity Score de uma empresa com
poucos dados nunca é artificialmente "puxado para baixo" ou "para cima" por
um dado que simplesmente não existe — ele reflete só o que foi de fato
observado.

`Website Gap` e `Contactability` são as únicas duas dimensões calculadas
SEMPRE (nunca excluídas): todo `AuditSnapshot` tem um `site_state` (mesmo
que `not_checked`), e a ausência de telefone/endereço/contato é, ela mesma,
um fato observável real sobre a empresa (o Discovery tenta coletar esses
campos sempre) — não um "não verificado".

## Confidence — separado do score

`OpportunityScore.confidence` (reaproveita `ConfidenceLevel`, Fase 0) reflete
**quantidade e qualidade do sinal disponível**, nunca o valor do score em
si. Regra (`app.domains.scoring.scoring._compute_confidence`):

- `site_state` em `not_checked`/`inconclusive` → sempre `LOW` (o próprio
  processo de auditoria não terminou de decidir o que existe).
- 5 ou 6 dimensões disponíveis → `HIGH`.
- 3 ou 4 dimensões disponíveis → `MEDIUM`.
- Menos de 3 → `LOW`.

Um score alto com confiança baixa é uma combinação válida e esperada (ex.:
poucos sinais, mas todos fortes e na mesma direção) — nunca "corrigimos" o
score por causa da confiança baixa, porque isso equivaleria a inventar um
ajuste sem base em dado nenhum.

## Classificação (tiers)

| Faixa | Tier |
|---|---|
| 80-100 | `high` |
| 60-79 | `medium_high` |
| 40-59 | `medium` |
| 20-39 | `low` |
| 0-19 | `very_low` |

Ampliado de 3 para 5 faixas em relação ao placeholder da Fase 0
(`OpportunityTier` tinha só `low`/`medium`/`high`) — nenhuma linha havia
sido persistida com esses valores antes da Fase 4 (o cálculo nunca rodou),
então não houve necessidade de migrar dado histórico, só o enum em código.

## `rating`/`review_count`: por que não é receita

`Business Visibility` usa `rating` e `review_count` (coletados pelo
Discovery/Google Places, Fase 1) exclusivamente como indício de que **o
negócio é real, ativo e encontrável** — nunca como proxy de faturamento,
orçamento ou capacidade de compra. Duas salvaguardas concretas, testadas em
`tests/scoring/test_scoring.py`:

1. **Peso moderado (15%)**: mesmo um sinal de visibilidade excelente não
   pode, sozinho, definir o score.
2. **Saturação**: `review_count` satura em 50 avaliações
   (`_REVIEW_COUNT_SATURATION`) — uma empresa com 50.000 avaliações produz
   exatamente o mesmo componente de visibilidade que uma com 50. O
   objetivo é distinguir "tem alguma tração pública" de "não tem nenhuma",
   nunca ranquear por popularidade (que se aproximaria perigosamente de
   usar reviews como proxy de sucesso financeiro).

## Segment Fit: tabela pequena, não uma nova taxonomia

`SEGMENT_FIT_SCORES` (`app.domains.scoring.scoring`) é um dicionário curto
(~15 entradas) mapeando `Category.slug` normalizado para um valor de
adequação 0-100, baseado no perfil de cliente típico de uma agência de
desenvolvimento web. Categorias fora da tabela recebem o valor neutro
`SEGMENT_FIT_DEFAULT = 50.0`, marcado explicitamente como tal no `reason`
do breakdown — nunca tratado com a mesma confiança de uma categoria
mapeada de propósito.

## Persistência e versionamento

`OpportunityScore` continua 1:1 com `AuditSnapshot` (`audit_snapshot_id`
único) — decisão já tomada na Fase 3 (ver `docs/data-model.md`) e mantida:
uma nova auditoria sempre gera um novo `AuditSnapshot` e, portanto, um novo
`OpportunityScore`, preservando o histórico de como a oportunidade evoluiu
ao longo do tempo. Recalcular o score do **mesmo** `AuditSnapshot`
(`OpportunityScoringService.compute` chamado de novo sem uma nova auditoria)
atualiza a linha existente em vez de criar uma segunda — isso só muda o
número quando a fórmula/versão (`scoring_version`) muda, e nesse caso
substituir o valor antigo pelo novo é a leitura mais simples e honesta do
que "o score deste snapshot" significa.

`scoring_version` (hoje `"v1"`, constante `SCORING_VERSION`) é persistido
em cada linha para que um score calculado com uma fórmula antiga continue
interpretável mesmo depois de uma recalibração futura dos pesos/dimensões.

`breakdown` (JSON) grava, por dimensão: valor bruto (`raw`), peso
(`weight`), contribuição para o score final (`contribution`), uma razão
textual curta (`reason`) e referências às `Evidence`/`WebsiteQuality`
usadas (`evidence_refs`) — nunca só o número final, para manter toda
decisão auditável (mesmo espírito do Website Quality Score, Fase 3).

## API

```
POST /api/scoring/{company_id}   → calcula (ou recalcula) o score da auditoria mais recente
GET  /api/scoring/{company_id}   → consulta o score mais recente
```

`POST` é sempre síncrono — ao contrário de Discovery/Digital Audit/Sales
Brief, o cálculo não chama nenhum provider externo, então não há motivo
para enfileirar. Erros de precondição (`company_id` inexistente, nenhuma
auditoria executada ainda) retornam `404`/`409` — nunca um score parcial ou
inventado.

## Limitações conhecidas

1. **Pesos, faixas de classificação e tabela de Segment Fit são hipóteses
   iniciais documentadas, não um resultado de dados reais** — no mesmo
   espírito dos limiares de Identity Resolution (Fase 2) e dos pesos do
   Website Quality Score (Fase 3). Aguardam recalibração quando houver
   dados reais de conversão/venda.
2. **Digital Presence Gap está estruturalmente subalimentado**: como
   nenhuma fase anterior tem um provider dedicado de redes sociais
   (Instagram Graph API, por exemplo, é só uma configuração reservada,
   nunca implementada), o único sinal disponível para esta dimensão é se o
   valor de "website" coletado pelo Google Places aponta para um domínio
   social/agregador — um sinal indireto e frequentemente ausente.
3. **Nenhum dado real de conversão de vendas foi usado para validar a
   fórmula** — os "casos importantes" descritos no Prompt 07 foram
   verificados por teste automatizado (`tests/scoring/test_scoring.py`)
   contra o comportamento da implementação, não contra histórico real de
   quais prospects de fato converteram.
