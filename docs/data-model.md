# Modelo de dados — Fase 2

Reflete exatamente o schema criado pelas migrations
`backend/migrations/versions/0001_initial_schema.py` (Fase 0),
`0002_discovery_search_run_details.py` (Fase 1) e
`0003_identity_resolution.py` (Fase 2), geradas a partir dos modelos em
`backend/app/domains/*/models.py`.

## Tabelas

| Tabela | Domínio | Papel |
|---|---|---|
| `companies` | companies | Identidade interna da empresa. **Não tem nenhuma coluna de identificador externo.** |
| `regions` | companies | Região geográfica normalizada. |
| `categories` | companies | Categoria/segmento normalizado. |
| `company_sources` | identity | Vínculo entre uma `Company` e uma fonte externa. `UNIQUE(source, external_id)`. **Alterada na Fase 2** — ganhou `latitude`/`longitude`. |
| `identity_merge_logs` | identity | Histórico de fusões/reversões de identidade entre duas `Company` já existentes. |
| `dedup_candidates` | identity | **Nova na Fase 2.** Toda decisão não trivial de Identity Resolution — auditoria e fila de revisão humana. |
| `evidence` | evidence | Fato individual com proveniência, append-only. |
| `audit_snapshots` | audit | Uma execução de auditoria sobre uma `Company`. |
| `website_quality_snapshots` | audit | Placeholder 1:1 com `audit_snapshots` para o Website Quality Score futuro. |
| `opportunity_scores` | scoring | Placeholder 1:1 com `audit_snapshots` para o Opportunity Score futuro. |
| `search_runs` | discovery | Uma execução de descoberta: critérios, status e contadores de resultado. |
| `provider_usage_records` | discovery | Uma linha por chamada real a um provider externo — base do rastreamento de custo. |

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
`SearchRunStatus`, e os dois novos da Fase 2 — `MatchDecision` e
`DedupCandidateStatus`) são declarados com `native_enum=False`. Isso os
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
recência entre fontes conflitantes** foi implementada — isso continua
reservado para a Fase 3 (Digital Auditor), que vai precisar decidir entre
valores concorrentes com pesos de confiança. O que a Fase 2 adicionou
(`app/domains/evidence/queries.py::get_current_evidence`) é mais simples:
como só existe uma `Evidence` não superada por `(company_id, field)` a
qualquer momento — cada novo valor supera o anterior via
`Evidence.mark_superseded_by()` — buscar "o valor atual" nunca tem empate
para resolver. Essa função é reaproveitada tanto pela persistência do
Discovery quanto pelo Identity Resolution (que precisa saber o telefone/
site/endereço atual de uma empresa para comparar contra um candidato).

## `AuditSnapshot`, `WebsiteQuality`, `OpportunityScore`: relação 1:1 com uma execução, não com a empresa

`website_quality_snapshots.audit_snapshot_id` e
`opportunity_scores.audit_snapshot_id` são `UNIQUE` — cada execução de
auditoria tem no máximo um resultado de qualidade e um score. Nenhum dos
dois se relaciona diretamente com `companies`: isso é o que preserva o
histórico de como a pontuação de uma empresa mudou ao longo do tempo, em
vez de sobrescrever um único campo em `Company`.

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
