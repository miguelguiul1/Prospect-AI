# Modelo de dados — Fase 1

Reflete exatamente o schema criado pelas migrations
`backend/migrations/versions/0001_initial_schema.py` (Fase 0) e
`0002_discovery_search_run_details.py` (Fase 1), geradas a partir dos
modelos em `backend/app/domains/*/models.py`.

## Tabelas

| Tabela | Domínio | Papel |
|---|---|---|
| `companies` | companies | Identidade interna da empresa. **Não tem nenhuma coluna de identificador externo.** |
| `regions` | companies | Região geográfica normalizada. |
| `categories` | companies | Categoria/segmento normalizado. |
| `company_sources` | identity | Vínculo entre uma `Company` e uma fonte externa. `UNIQUE(source, external_id)`. |
| `identity_merge_logs` | identity | Histórico de fusões/reversões de identidade entre duas `Company`. |
| `evidence` | evidence | Fato individual com proveniência, append-only. |
| `audit_snapshots` | audit | Uma execução de auditoria sobre uma `Company`. |
| `website_quality_snapshots` | audit | Placeholder 1:1 com `audit_snapshots` para o Website Quality Score futuro. |
| `opportunity_scores` | scoring | Placeholder 1:1 com `audit_snapshots` para o Opportunity Score futuro. |
| `search_runs` | discovery | Uma execução de descoberta: critérios, status e contadores de resultado. **Alterada na Fase 1** — ver abaixo. |
| `provider_usage_records` | discovery | **Nova na Fase 1.** Uma linha por chamada real a um provider externo — base do rastreamento de custo. |

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
`SearchRunStatus`) são declarados com `native_enum=False`. Isso os
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

Nenhuma lógica de "resolver o valor atual de um campo" (por confiança +
recência) foi implementada — isso pertence à Fase 3, quando o Digital
Auditor de fato precisar consumir esse histórico. A Fase 0 só garante que
a estrutura suporta o padrão append-only:
`Evidence.mark_superseded_by()` aponta a linha antiga para a nova via
`superseded_by_id`, sem jamais editar `value`/`state` no lugar.

## `AuditSnapshot`, `WebsiteQuality`, `OpportunityScore`: relação 1:1 com uma execução, não com a empresa

`website_quality_snapshots.audit_snapshot_id` e
`opportunity_scores.audit_snapshot_id` são `UNIQUE` — cada execução de
auditoria tem no máximo um resultado de qualidade e um score. Nenhum dos
dois se relaciona diretamente com `companies`: isso é o que preserva o
histórico de como a pontuação de uma empresa mudou ao longo do tempo, em
vez de sobrescrever um único campo em `Company`.

## Tabelas que a v0.2 descreve mas a Fase 0 não cria

`DedupCandidate` existe na arquitetura v0.2 (fila de revisão humana para
casos ambíguos de deduplicação), mas **não foi criada nesta fase**: o
prompt de implementação da Fase 0 lista explicitamente as entidades
esperadas (`Company`, `CompanySource`, `Evidence`, `AuditSnapshot`,
`WebsiteQuality`, `OpportunityScore`, `SearchRun`, `IdentityMergeLog`) e
`DedupCandidate` não está entre elas — corretamente, já que a lógica que a
usaria (correspondência difusa, fila de revisão) é escopo da Fase 2. Ela
será adicionada quando a Identity Resolution for implementada.

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
