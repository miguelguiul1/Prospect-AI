# Identity Resolution — Fase 2

> Identity Resolution decide se um candidato recém-descoberto é uma
> empresa já conhecida ou uma nova. Ele não avalia oportunidade comercial,
> qualidade de site nem prioriza nada — isso é trabalho das fases 3 e 4.

## Objetivo

Responder, para cada resultado que o Discovery (Fase 1) produz e cujo
`(source, external_id)` é inédito: "essa observação pertence a uma
`Company` que já conhecemos, ou é uma empresa nova?" — com uma regra clara
para quando a resposta é "não sei" (nunca decide um merge no escuro).

## Princípio central: falso positivo é pior que falso negativo

É preferível manter duas empresas separadas do que uni-las
incorretamente. Por isso:

- **MATCH automático** só ocorre com um sinal forte (telefone igual, ou
  site oficial igual) **combinado** com um segundo sinal compatível (nome
  ou endereço). Nenhum sinal isolado é suficiente — nem telefone igual
  sozinho, nem nome idêntico sozinho, nem proximidade geográfica sozinha.
- **Contradições concretas** (telefones diferentes e conhecidos dos dois
  lados; regiões diferentes e conhecidas dos dois lados) resultam em
  `NO_MATCH` direto, mesmo com nomes muito parecidos.
- **Tudo o que sobra** — sinal parcial, corroboração fraca, informação
  insuficiente — vira `INCONCLUSIVE`. Nunca um merge automático; fica
  registrado para revisão humana futura.

## Sinais usados

| Sinal | Papel |
|---|---|
| `(source, external_id)` idêntico | Não passa pelo matcher — é resolvido antes, na persistência (Fase 1), por ser uma correspondência exata e determinística. |
| Telefone normalizado igual | Forte — mas só decide combinado com nome ou endereço compatível. |
| Domínio de site **oficial** igual | Forte — nunca conta se o domínio for de rede social/agregador/marketplace (ver lista em `app/domains/identity/matching.py`). |
| Nome (RapidFuzz `token_sort_ratio`, após dobrar maiúsculas/acentos) | Apoio — nunca decide sozinho. |
| Endereço (mesma técnica) | Apoio — nunca decide sozinho. |
| Região (`Region` da busca) | Contradição concreta quando diferente e conhecida dos dois lados. |
| Categoria | Apoio fraco. |
| Distância geográfica (Haversine) | Apoio — nunca decide sozinho; duas empresas diferentes podem dividir prédio/galeria. |

Todos os limiares (`IDENTITY_NAME_SIMILARITY_THRESHOLD=75`,
`IDENTITY_ADDRESS_SIMILARITY_THRESHOLD=85`,
`IDENTITY_GEO_PROXIMITY_METERS=150`) são configuráveis e foram calibrados
manualmente contra os exemplos desta fase — não contra dados reais. A
arquitetura v0.2 já previa que precisariam de recalibração futura.

## Estados de decisão

`MatchDecision`: `MATCH` / `NO_MATCH` / `INCONCLUSIVE` (reaproveita
`ConfidenceLevel` — HIGH/MEDIUM/LOW — do Evidence Layer da Fase 0 para o
grau de confiança, sem duplicar esse enum).

## Fluxo dentro do Discovery

```
Discovery encontra (source, external_id) inédito
        │
        ▼
Existe CompanySource com esse (source, external_id)? ──sim──► reaproveita a Company (Fase 1, inalterado)
        │ não
        ▼
IdentityResolutionService.find_candidates()
  (telefone atual igual ∪ site oficial atual igual ∪ mesma região)
        │
        ▼
resolve() contra cada candidato
        │
   ┌────┴────┬───────────────┐
  MATCH   INCONCLUSIVE    NO_MATCH
   │            │               │
   ▼            ▼               ▼
reaproveita   cria Company    cria Company
a Company     nova + registra nova + registra
existente     DedupCandidate  DedupCandidate
(sem nova     (pending_review) (auto_resolved)
Company)
```

Nenhuma alteração de contrato foi feita no Discovery: `find_or_create_company`
continua devolvendo `(Company, created: bool)`; `DiscoveryService.execute()`
ganhou uma linha para construir e repassar o `IdentityResolutionService`. Ver
`docs/discovery.md` para o resto do fluxo, inalterado.

## `Company` continua independente de qualquer fonte

Nenhuma mudança na regra da Fase 0: `Company` não ganhou nenhum campo de
identificador externo. O que mudou é que agora **múltiplas** linhas de
`CompanySource` — de fontes diferentes — podem apontar para a mesma
`Company` como resultado de uma decisão de matching, não só de uma
correspondência exata.

## `DedupCandidate`: uma tabela para auditoria e para revisão

Anunciada como pendente desde a Fase 0 ("será adicionada quando a Identity
Resolution for implementada" — `docs/data-model.md`). Cobre os dois papéis
que a Fase 2 pede (seção 3.4 do prompt) numa única tabela, em vez de duas:

- **Toda decisão não trivial** vira uma linha — `MATCH`, `NO_MATCH` ou
  `INCONCLUSIVE` — com `company_id` (a empresa existente comparada),
  `resulting_company_id` (a empresa à qual a fonte nova acabou associada),
  `reasons`, `signals`, `confidence` e `decided_by`.
- `status=auto_resolved` para decisões confiantes (`MATCH`/`NO_MATCH`);
  `status=pending_review` exclusivamente para `INCONCLUSIVE` — é a fila de
  revisão humana. `CONFIRMED_SAME`/`CONFIRMED_DIFFERENT` existem para uma
  revisão futura marcar o desfecho; nenhum código desta fase os atribui.

Quando não há nenhum candidato para comparar (base vazia para aquele
sinal), nada é gravado — não há o que auditar.

## Merge de duas `Company` já existentes

Capacidade separada do fluxo acima (`IdentityResolutionService.
merge_companies`): funde duas `Company` que já existem como registros
distintos — cenário diferente de "anexar uma fonte nova a uma empresa
existente", que nunca envolve uma segunda `Company` já persistida.

**Escolha da canônica** (determinística, nesta ordem): mais
`CompanySource` vinculadas vence primeiro (identidade mais corroborada
entre fontes); empate por mais `Evidence` (dado mais completo); empate
seguinte por `created_at` mais antigo (registro mais estabelecido);
desempate final por menor UUID (só para nunca depender da ordem de
leitura do banco).

**Preservação de dados**: `CompanySource` e `Evidence` da empresa
descartada são reassociados à canônica pelo atributo de relationship
(`source.company = primary`), nunca pela coluna de FK direta — as
relationships `Company.sources`/`Company.evidences` têm cascade
`delete-orphan`, e reatribuir só a coluna de FK arriscaria uma exclusão
silenciosa dessas linhas. A empresa descartada é marcada `ARCHIVED`
(reaproveitando `CompanyStatus`, que já existia desde a Fase 0), nunca
apagada — preserva a possibilidade de auditar ou reverter depois
(`IdentityMergeLog.reverted_at`). Testado explicitamente em
`tests/identity/test_service.py::TestMergeCompanies::
test_merge_reassigns_sources_and_evidence_without_data_loss`.

**Não exposto por HTTP nesta fase**: fundir duas empresas é uma operação
pouco frequente e de impacto alto, e este sistema ainda não tem nenhuma
camada de autenticação/autorização (nenhuma fase até aqui implementou
login). Expor `merge_companies` como endpoint sem controle de acesso
violaria a própria orientação da Fase 2 ("não exponha operações
perigosas de merge irreversível sem controles adequados") — fica para
quando essa camada existir (Fase 5/dashboard).

## Geolocalização: por que não PostGIS

A arquitetura oficial usa PostgreSQL simples — a imagem do
`docker-compose.yml` é `postgres:16-alpine`, sem a extensão PostGIS
provisionada, nem em Fase 0/1 nem agora. Introduzir PostGIS exigiria
infraestrutura que não existe em nenhum ambiente deste projeto ainda.
A distância é calculada em Python puro (fórmula de Haversine,
`app/domains/identity/geo.py`) sobre um conjunto já filtrado de poucos
candidatos (nunca a tabela inteira) — suficiente nesta escala. Migrar
para `ST_DWithin`/PostGIS fica como otimização futura de performance, não
uma mudança de arquitetura.

## API

```
POST /api/identity/resolve
```

Só leitura: recebe os dados de um candidato (mesmo formato que o Discovery
produziria) e devolve a decisão que o matcher tomaria, sem persistir nada.
Serve para inspecionar/depurar o matching sem rodar uma busca de Discovery
inteira. Nenhum endpoint de merge é exposto (ver acima).

## Casos conflitantes entre fontes

Quando duas fontes discordam sobre um campo (ex.: telefones diferentes),
o Identity Resolution nunca "resolve" o conflito escolhendo um valor —
ele só decide se as duas observações são a mesma empresa. Se decidir que
sim (`MATCH`) e os valores realmente divergirem em campos que não
entraram na decisão, ambos ficam gravados como `Evidence` distintas (a
mais recente supera a anterior, no mesmo padrão append-only da Fase 0/1) —
qual delas é "a verdadeira" continua sendo uma pergunta para a Fase 3
(Digital Auditor), não para esta fase.

## Limitações desta fase

- Limiares de similaridade são hipóteses calibradas à mão, não a partir de
  dados reais de conversão.
- Sem PostGIS: distância calculada em Python, adequada à escala de um
  conjunto de candidatos já filtrado, não à tabela inteira.
- Nenhuma revisão humana das filas `pending_review` foi implementada —
  a tabela existe e é populada; consumi-la é trabalho de uma fase futura
  (dashboard).
- `merge_companies` não é exposto por HTTP (ver acima) — só testado na
  camada de serviço.
- O bloqueio (`find_candidates`) usa no máximo os primeiros 50 registros
  por região — suficiente para o volume desta fase, mas não pensado para
  uma base de centenas de milhares de empresas por região.

## Testes

48 testes cobrem este domínio (`backend/tests/identity/` e
`backend/tests/discovery/test_identity_integration.py`): geolocalização,
os nove casos de exemplo da Fase 2 (B a I aplicados ao matcher puro — A é
a correspondência exata, já coberta pelos testes de Discovery),
construção de perfil a partir de `Evidence`, bloqueio de candidatos,
resolução fim-a-fim persistida, `DedupCandidate`, `merge_companies`
(incluindo a trava contra perda de dados do cascade `delete-orphan`), a
API de resolução, e um teste de integração completo com duas fontes
diferentes para a mesma empresa. Nenhum teste depende de rede.
