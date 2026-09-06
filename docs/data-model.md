# Modelo de dados — Fase 6

Reflete exatamente o schema criado pelas migrations
`backend/migrations/versions/0001_initial_schema.py` (Fase 0),
`0002_discovery_search_run_details.py` (Fase 1),
`0003_identity_resolution.py` (Fase 2), `0004_digital_audit.py` (Fase 3),
`0005_opportunity_scoring_and_sales_brief.py` (Fase 4) e
`0006_prototype_builder.py` (Fase 6 — a Fase 5 não alterou o schema),
geradas a partir dos modelos em `backend/app/domains/*/models.py`.

## Tabelas

| Tabela | Domínio | Papel |
|---|---|---|
| `companies` | companies | Identidade interna da empresa. **Não tem nenhuma coluna de identificador externo.** |
| `regions` | companies | Região geográfica normalizada. |
| `categories` | companies | Categoria/segmento normalizado. |
| `company_sources` | identity | Vínculo entre uma `Company` e uma fonte externa. `UNIQUE(source, external_id)`. Ganhou `latitude`/`longitude` na Fase 2. |
| `identity_merge_logs` | identity | Histórico de fusões/reversões de identidade entre duas `Company` já existentes. |
| `dedup_candidates` | identity | Toda decisão não trivial de Identity Resolution — auditoria e fila de revisão humana. |
| `evidence` | evidence | Fato individual com proveniência, append-only. |
| `audit_snapshots` | audit | Uma execução de auditoria sobre uma `Company`. **Alterada na Fase 3** — ver abaixo. |
| `website_quality_snapshots` | audit | Website Quality Score. **Alterada na Fase 3** — deixou de ser placeholder. |
| `opportunity_scores` | scoring | O Opportunity Score, 1:1 com `audit_snapshots`. **Implementado na Fase 4** — ver abaixo. |
| `sales_briefs` | briefing | Um Sales Brief gerado (ou uma tentativa falha) para uma empresa. **Nova na Fase 4** — ver abaixo. |
| `search_runs` | discovery | Uma execução de descoberta: critérios, status e contadores de resultado. |
| `provider_usage_records` | discovery | Uma linha por chamada real a um provider externo — base do rastreamento de custo. |
| `prototypes` | prototypes | Um protótipo do Prototype Builder (Fase 6). **Nova na Fase 6** — ver abaixo. Sem relação com `companies`. |

## Por que `Company` não tem `place_id`

Esta é a correção central da arquitetura v0.2 em relação à v0.1: nenhuma
coluna de `companies` referencia uma fonte externa. `place_id` do Google,
`osm_id` do OpenStreetMap, CNPJ, ID de conta do Instagram — todos vivem em
`company_sources`, nunca em `companies`. O teste
`test_models.py::TestCompanyIdentity::test_company_has_no_external_identifier_column`
existe para travar essa regra: se alguém adicionar uma coluna como
`place_id` a `Company` no futuro, o teste falha imediatamente.

## `CompanySource`: por que `source` é uma string livre, não um Enum de banco

`confidence` (em `CompanySource` e em `Evidence`) e `state` (em `Evidence`)
usam `Enum` do SQLAlchemy porque são vocabulários pequenos e centrais à
arquitetura — mudá-los é uma decisão deliberada que deve exigir uma
migration.

`source`, em vez disso, é uma `String(60)` indexada. Fontes novas (uma
rede social diferente, um novo provedor de dados de CNPJ) devem poder ser
adicionadas sem uma migration de schema — só passam a aparecer como um
novo valor de string. Constrangimento de valores válidos, quando for
necessário, deve ser feito na camada de aplicação (validação de entrada do
job de Discovery/Identity Resolution), não no banco.

## Enums em `native_enum=False`

Todos os `Enum` do SQLAlchemy usados neste schema (`CompanyStatus`,
`ConfidenceLevel`, `EvidenceMethod`, `DataState`, `OpportunityTier`,
`SearchRunStatus`, `MatchDecision`/`DedupCandidateStatus` da Fase 2,
`AuditStatus` da Fase 3, e `SalesBriefStatus`, novo na Fase 4) são
declarados com `native_enum=False`. Isso os
armazena como `VARCHAR` (com validação do lado da aplicação) em vez de um
tipo `ENUM` nativo do PostgreSQL. A troca é deliberada: adicionar um novo
valor a um `ENUM` nativo do Postgres exige `ALTER TYPE`, uma operação mais
delicada de migrar em produção do que simplesmente passar a aceitar um
novo valor de string. Como todos esses vocabulários (especialmente
`DataState`) são exatamente o tipo de coisa que pode ganhar um valor novo
à medida que a Fase 3 é implementada, portabilidade de evolução venceu a
garantia extra de integridade que um `ENUM` nativo daria.

## `Evidence`: campo `state` vs. campo `value`

Uma linha de `Evidence` sempre tem um `state` (`DataState`) e pode ou não
ter um `value`. Isso cobre dois casos com a mesma estrutura:

- Um fato positivo (ex.: `field="phone", value="+55...", state=CONFIRMED`).
- O resultado de uma checagem sem valor (ex.:
  `field="website", value=None, state=INCONCLUSIVE"`).

Nenhuma lógica de "resolver o valor atual de um campo" **por confiança e
recência entre fontes conflitantes** foi implementada — a Fase 3 (Digital
Audit) usa `state` para o que ela de fato precisa (distinguir
`confirmed`/`inconclusive`/`inaccessible`/`not_checked` de uma checagem
própria), mas ainda não arbitra entre DOIS valores concorrentes de fontes
diferentes com pesos de confiança; isso seguirá reservado para quando essa
necessidade concreta aparecer. O que já existe desde a Fase 2
(`app/domains/evidence/queries.py::get_current_evidence`) é mais simples:
como só existe uma `Evidence` não superada por `(company_id, field)` a
qualquer momento — cada novo valor supera o anterior via
`Evidence.mark_superseded_by()` — buscar "o valor atual" nunca tem empate
para resolver. A Fase 3 generalizou essa mesma função em
`upsert_evidence` (aceitando `state`/`audit_snapshot_id` variáveis) para
gravar seus próprios sinais sem duplicar a lógica do Discovery.

## `AuditSnapshot`, `WebsiteQuality`, `OpportunityScore`: relação 1:1 com uma execução, não com a empresa

`website_quality_snapshots.audit_snapshot_id` e
`opportunity_scores.audit_snapshot_id` são `UNIQUE` — cada execução de
auditoria tem no máximo um resultado de qualidade e um score. Nenhum dos
dois se relaciona diretamente com `companies`: isso é o que preserva o
histórico de como a pontuação de uma empresa mudou ao longo do tempo, em
vez de sobrescrever um único campo em `Company`.

## `audit_snapshots` e `website_quality_snapshots` na Fase 3

`AuditSnapshot` ganhou as colunas que uma execução real de auditoria
precisa registrar: `website_url` (a URL efetivamente auditada — pode
diferir do `website` corrente em `Evidence` se o candidato mudou depois),
`site_state` (reaproveita `DataState` da Fase 0 — `confirmed`/
`not_detected`/`inconclusive`/`inaccessible`/`not_checked`), `status`
(novo enum `AuditStatus`: `pending`/`running`/`completed`/`failed` —
descreve se o PROCESSO rodou bem, não o que foi encontrado; um site
inacessível é `status=completed` com `site_state=inaccessible`, nunca
`status=failed`), `started_at`/`finished_at` e `error_code`/
`error_message` (usados também para anotar decisões não-erro, como um
bloqueio de SSRF). `presence_level` permanece um placeholder — sua
semântica na v0.2 é mais ampla (síntese incluindo redes sociais) do que o
que a Fase 3 avalia.

`WebsiteQuality` ganhou `components` (score por dimensão — segurança/SEO/
conteúdo/UX/técnico), `confidence` (reaproveita `ConfidenceLevel`) e
`limitations` (por que o score pode estar incompleto). `score`/
`confidence`/`components` ficam todos `NULL` quando `site_state !=
confirmed` — nunca um `0` que pareça dizer "site ruim" quando na verdade
significa "não avaliável". Ver `docs/digital-audit.md` para a metodologia
completa.

## `opportunity_scores` na Fase 4

Ganhou `confidence` (reaproveita `ConfidenceLevel`), `scoring_version`
(string curta, hoje `"v1"`) e `updated_at` — aditivo, sem remover nenhum
campo existente desde a Fase 0. `tier` passou de 3 para 5 valores
(`OpportunityTier`: `high`/`medium_high`/`medium`/`low`/`very_low`); como
nenhuma linha tinha `tier` preenchido antes da Fase 4 (o cálculo nunca
rodou), não houve dado histórico para migrar. `breakdown` (já existia como
placeholder) agora é populado de verdade: por dimensão, valor bruto, peso,
contribuição, razão textual e referências de evidência — ver
`docs/opportunity-scoring.md`.

Recalcular o score do MESMO `audit_snapshot_id` atualiza a linha existente
em vez de criar uma segunda (a `UNIQUE` em `audit_snapshot_id`, existente
desde a Fase 0, impede duas linhas para a mesma execução de auditoria) — o
histórico de como a empresa evoluiu já é preservado pela cadeia de
`AuditSnapshot` (uma nova auditoria sempre gera um novo snapshot e,
portanto, um novo score).

## `sales_briefs` (Fase 4)

Nova tabela, sem relação 1:1 com nada — `company_id` e
`opportunity_score_id` são só `index`, não `unique`, porque o histórico de
Sales Briefs de uma empresa é intencionalmente preservado (cada
`POST /api/sales-brief/{company_id}` cria uma linha nova, nunca sobrescreve
uma anterior, mesmo em caso de falha). `status` (`SalesBriefStatus`:
`completed`/`failed`) descreve se a geração teve sucesso; `content` (JSON)
fica `NULL` quando `status=failed` — nunca um conteúdo parcial ou
inventado. `error_code`/`error_message` só são preenchidos em caso de
falha. `input_tokens`/`output_tokens`/`duration_ms` só são preenchidos
quando o próprio provider os informa — nunca estimados. Ver
`docs/sales-brief.md` para o desenho completo.

O vínculo com `opportunity_score_id` (em vez de `audit_snapshot_id`
diretamente) ancora qual versão exata dos dados (via
`OpportunityScore.scoring_version` e a cadeia até o `AuditSnapshot` que o
gerou) fundamentou aquele briefing — dispensa um campo extra de "versão de
contexto".

## `prototypes` (Fase 6)

Tabela isolada, sem chave estrangeira para `companies` nem para nenhuma
outra tabela — o Prototype Builder é uma ferramenta independente, não um
estágio do pipeline de prospecção (ver `docs/architecture.md`). `owner_id`
existe (`String`, nullable, indexado) mas não é preenchido nem usado para
autorizar nada nesta fase: uma auditoria confirmou que o Prospect AI não
tem autenticação em nenhuma fase até aqui, então não há usuário para
associar — reservado para quando uma fase futura de autenticação existir,
no mesmo espírito de `search_runs.requested_by` (Fase 1). Ver
`docs/prototype-builder.md` para a discussão completa.

`components` (JSON) guarda a árvore de componentes como uma **lista
plana** — cada item tem `parent_id`/`order`, não uma estrutura de
`children` aninhados — validada inteira (tipos, ciclos, profundidade,
tamanho) por `app.domains.prototypes.schemas.validate_component_tree`
antes de qualquer persistência. `settings` (JSON) fica reservado para
configuração do protótipo como um todo (ex.: dimensões do canvas),
nenhuma ainda é lida por código desta fase.

## `dedup_candidates` (Fase 2): uma tabela para dois papéis

A arquitetura v0.2 previa `DedupCandidate` como fila de revisão humana
para casos ambíguos, separada de um log de auditoria — a Fase 0/1 adiou
sua criação exatamente para a Fase 2. Implementada agora, ela cobre os
dois papéis numa única tabela, em vez de duas: toda decisão não trivial
de Identity Resolution (`MATCH`, `NO_MATCH` ou `INCONCLUSIVE`) vira uma
linha, com `status=auto_resolved` para as duas primeiras e
`status=pending_review` só para `INCONCLUSIVE` — a fila de revisão é
literalmente o filtro por esse status, não uma tabela à parte. Ver
`docs/identity-resolution.md` para o desenho completo e o porquê.

`IdentityMergeLog` continua com seu papel original e inalterado: histórico
de fusão entre duas `Company` **já existentes** como registros separados
— um cenário diferente de "associar uma fonte nova a uma empresa
existente", que nunca envolve uma segunda `Company` já persistida.

## `search_runs`: de intenção a execução rastreável (Fase 1)

A Fase 0 criava `SearchRun` só como intenção (`region_query`,
`segment_query`, `status`). A Fase 1 adiciona o que uma execução real
precisa registrar: `provider`, `parameters` (a `DiscoveryQuery` validada e
normalizada — nunca a entrada bruta do operador), `raw_result_count`,
`normalized_result_count`, `persisted_count`, `new_company_count`,
`pages_fetched`, `error_code`/`error_message`, `cost_estimate`/
`cost_currency`. `status` ganha dois valores (`partially_completed`,
`cancelled`) — como já era `native_enum=False` (seção acima), isso não
exigiu `ALTER TYPE`, só uma migration comum que amplia o `VARCHAR`.

## `provider_usage_records`: custo por chamada, não por busca

Uma linha por chamada HTTP real a um provider (uma página = uma linha) —
nunca por resultado retornado. Existe separada de `search_runs` para
responder "por que esta busca custou tanto" com granularidade por chamada
(arquitetura v0.2, seção 20), e porque uma busca paginada faz várias
chamadas com custo potencialmente somável. `estimated_cost` fica nulo
quando nenhum preço foi configurado (`Settings.discovery_cost_per_request`)
— o sistema sempre sabe *quantas* chamadas fez, mesmo sem saber quanto
cada uma custou.

## `company_sources.latitude`/`longitude` (Fase 2)

Coordenadas pertencem à fonte, não à `Company` — o mesmo espírito de
`source_url`: é um dado que uma fonte específica reportou, não um atributo
canônico da empresa (fontes diferentes podem discordar ligeiramente, ou
uma pode não reportar coordenada nenhuma). Usadas como sinal de apoio pelo
Identity Resolution (`app/domains/identity/profile.py`), nunca como
critério isolado — ver `docs/identity-resolution.md`. Sem PostGIS: são
colunas `Float` simples, e a distância é calculada em Python
(Haversine), não numa consulta espacial do banco — a arquitetura oficial
continua sendo PostgreSQL simples, sem a extensão PostGIS provisionada em
nenhum ambiente deste projeto.

## Por que a Region/Category de uma empresa vem da busca, não do resultado

`Company.region_id`/`category_id` são resolvidos a partir da
`DiscoveryQuery` que a descobriu (`city`/`region`/`state`/`country` e
`category` informados pelo operador), não de uma decomposição do endereço
retornado pelo provider. O FieldMask do Google Places usado nesta fase
(`docs/discovery.md`) não inclui `addressComponents` — só
`formattedAddress`, uma string única — então não há como extrair
cidade/estado estruturados de cada resultado individual sem um campo
adicional (mais caro) que esta fase decidiu não solicitar.

## JSON, não JSONB

Colunas de dado semiestruturado (`raw_reference`, `signals`, `breakdown`)
usam o tipo genérico `JSON` do SQLAlchemy, que no PostgreSQL renderiza como
`JSON`, não `JSONB`. Portabilidade entre o Postgres real (Docker) e o
SQLite usado para rodar os testes nesta máquina (ver `development.md`)
pesou mais, nesta fase, do que o ganho de indexação binária do `JSONB` —
que ainda não tem nenhuma consulta que dependa dele. Migrar essas colunas
para `JSONB` mais adiante é uma migration aditiva simples, não uma
mudança de conceito.
