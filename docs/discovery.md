# Discovery — Fase 1

> Discovery encontra candidatos. Ele não determina identidade definitiva,
> qualidade do website ou oportunidade comercial.

## Objetivo

Responder, para uma região e um segmento de negócio, "quais empresas
potencialmente correspondem a esses critérios?" — consultando uma fonte
externa autorizada, normalizando o resultado e persistindo-o de forma
rastreável. Nada além disso.

Discovery explicitamente **não decide**:

- se dois registros são a mesma empresa (Identity Resolution, Fase 2);
- se uma empresa tem ou não site próprio (Digital Audit, Fase 3);
- se uma empresa é uma boa oportunidade comercial (Opportunity Score, Fase 4).

## Fluxo

```
Região + segmento (DiscoveryQuery, validado)
        │
        ▼
   SearchRun (PENDING)
        │
        ▼
DiscoveryJob / enqueue_or_run_discovery
        │
        ▼
DiscoveryService.execute()
        │
        ├─► Provider.search()  (Google Places, por página)
        │        │
        │        ├─ cache best-effort (Redis) ─┐
        │        └─ ProviderUsageRecord (1 por chamada real)
        │
        ├─► normalização (nome, endereço, telefone, URL, categoria)
        │
        └─► persistência
                 ├─ Company (find-or-create via CompanySource)
                 ├─ CompanySource (source, external_id, confidence)
                 └─ Evidence (append-only, só para campos observados)
        │
        ▼
   SearchRun (COMPLETED / PARTIALLY_COMPLETED / FAILED)
```

## Providers

`DiscoveryService` depende só da interface `DiscoveryProvider`
(`app/domains/discovery/providers/base.py`) — nunca de uma implementação
concreta. Isso é o que permite adicionar um novo provider sem alterar o
domínio de Discovery.

| Provider | Status |
|---|---|
| `google_places` | Implementado (Google Places API **New** — não a Legacy). |
| OpenStreetMap | **Não implementado.** A interface suporta, mas a Overpass API tem modelo de dados (tags livres, sem tipagem fixa de categoria) e política de uso comunitária que exigiriam uma camada de mapeamento própria — complexidade desproporcional ao valor desta fase. Fica documentado como extensão futura, não como um stub de código morto. |
| Fonte comercial licenciada | Não implementado — mencionado na arquitetura v0.2 como possibilidade futura. |

Trocar de provider é configurável via `DISCOVERY_PROVIDER` (ou o campo
`provider` de uma `DiscoveryQuery` individual, que tem prioridade).

## Google Places API (New)

Implementado contra a documentação oficial atual — **não** a Legacy API
(`maps.googleapis.com/maps/api/place/...`).

| Item | Valor |
|---|---|
| Text Search | `POST https://places.googleapis.com/v1/places:searchText` |
| Nearby Search | `POST https://places.googleapis.com/v1/places:searchNearby` |
| Autenticação | Header `X-Goog-Api-Key` |
| Campos retornados | Header `X-Goog-FieldMask` (obrigatório — a API rejeita a chamada sem ele) |

**Quando cada operação é usada:** `DiscoveryQuery` com `latitude`+`longitude`+`radius_km` usa Nearby Search; sem coordenadas (região/cidade por nome) usa Text Search — a mesma divisão descrita na arquitetura da Fase 1.

**FieldMask usado** (`app/domains/discovery/providers/google_places.py`):

```
places.id, places.displayName, places.formattedAddress, places.location,
places.primaryType, places.businessStatus, places.googleMapsUri,
places.internationalPhoneNumber, places.websiteUri, places.rating,
places.userRatingCount
```

mais `nextPageToken` (só na Text Search — a documentação da Nearby Search
não descreve suporte a paginação). Cada campo existe porque um campo do
DTO `DiscoveredCompany` depende diretamente dele — nenhum foi incluído
"por via das dúvidas" para uma fase futura. Em particular, **não**
solicitamos `places.types` (usamos só `primaryType`, um valor só) nem
`places.addressComponents` (ficaríamos só com `formattedAddress` como uma
string; decompor endereço em cidade/estado/bairro estruturados não é feito
nesta fase).

Cada campo tem um nível de SKU documentado por
[developers.google.com/.../data-fields](https://developers.google.com/maps/documentation/places/web-service/data-fields)
(Essentials/Pro/Enterprise) — anotado como comentário no código só como
referência de leitura. **Nenhum preço é hardcoded**: `nationalPhoneNumber`,
`websiteUri`, `rating` e `userRatingCount` estão no nível mais caro
(Enterprise) documentado; ainda assim são solicitados porque são
exatamente os campos que o DTO de Discovery desta fase precisa (seção 6 do
prompt de implementação). Ver "Custos" abaixo.

**Paginação:** Text Search devolve até 60 resultados no total, 20 por
página, via `nextPageToken`. Ao paginar, a documentação exige que todos os
parâmetros da chamada (exceto `pageToken`/`pageSize`) permaneçam idênticos
à primeira chamada — o provider reconstrói o corpo da requisição a partir
da mesma `DiscoveryQuery` a cada página, nunca de um estado parcial.
Nearby Search não pagina (não há `nextPageToken` documentado para ela);
`DiscoveryService` só faz uma chamada nesse caso.

**Tratamento de erro:**

| HTTP | Exceção interna | Retry? |
|---|---|---|
| 200 | — | — |
| 400 | `ProviderRequestError` | Não — parâmetro inválido é permanente |
| 401 / 403 | `ProviderRequestError` | Não — credencial inválida é permanente |
| 429 | `ProviderRateLimitedError` | Sim, com backoff, até o limite configurado |
| 5xx | `ProviderTemporaryError` | Sim, com backoff, até o limite configurado |
| timeout / erro de conexão | `ProviderTemporaryError` | Sim, com backoff, até o limite configurado |

Retry usa backoff exponencial (`discovery_http_backoff_base_seconds *
2^tentativa`, limitado por `discovery_http_backoff_max_seconds`) e para
definitivamente após `discovery_http_max_retries` tentativas extras —
nunca retry infinito. Se as tentativas se esgotarem (ou o erro não for
retryable), `DiscoveryService` interrompe a paginação daquele `SearchRun`:
marca `partially_completed` se algum resultado já tinha sido persistido, ou
`failed` caso contrário. Nunca tenta contornar o limite reportado pelo
provider.

**Limitações conhecidas:**

- Nenhum preço/cota oficial é assumido pelo código — valores reais mudam e
  devem ser confirmados na conta do Google Cloud do operador
  (`VALIDAR NA IMPLEMENTAÇÃO`, seguindo a convenção da arquitetura v0.2).
- A API legada exigia um pequeno intervalo antes de usar um
  `nextPageToken`; não confirmamos se a API New ainda exige isso. Fica
  configurável (`DISCOVERY_PAGE_TOKEN_DELAY_SECONDS`, padrão `0`) para
  quem observar erros de paginação em uso real.
- Sem `addressComponents`, os campos `city`/`state` do resultado
  individual (`DiscoveredCompany`) ficam sempre `None` — a `Region` de uma
  empresa descoberta vem dos critérios da própria busca (`DiscoveryQuery`),
  não de uma decomposição do endereço retornado.

## Estados de um `SearchRun`

| Estado | Significado |
|---|---|
| `pending` | Criado, ainda não iniciado. |
| `running` | Em execução. |
| `completed` | Terminou sem nenhum erro de provider. |
| `partially_completed` | Um erro interrompeu a busca, mas ao menos um resultado já tinha sido persistido. |
| `failed` | Um erro interrompeu a busca antes de persistir qualquer resultado (inclui provider não configurado/desconhecido). |
| `cancelled` | Reservado para uso futuro (ex.: cancelamento manual pelo operador) — nenhum código desta fase o atribui ainda. |

Nunca marcado `completed` quando uma falha impediu a execução inteira —
critério explícito da Fase 1.

## Identidade e proveniência

- `Company` nunca recebe um `place_id` (ou qualquer identificador
  externo) diretamente — a ligação vive em `CompanySource`
  (`source="google_places"`, `external_id=<place_id>`), com
  `confidence=high` (dado estruturado direto da fonte).
- Reprocessar a mesma busca é idempotente: `(source, external_id)` já
  conhecido nunca cria uma segunda `Company` — apenas atualiza
  `last_seen_at`/`raw_reference`.
- Cada campo observado (`name`, `address`, `phone`, `website`, `category`,
  `business_status`, `rating`, `review_count`) vira uma `Evidence` com
  `method=structured_field`, `confidence=high`, `source=google_places` e
  `collected_at`. Um campo ausente na resposta **nunca** gera uma
  `Evidence` — ausência não é o mesmo que "não existe" (isso é conclusão
  da Fase 3).
- Reexecutar a mesma busca com um valor que não mudou não cria uma nova
  `Evidence` (evita crescimento infinito por reprocessamento idêntico); um
  valor que mudou cria uma nova `Evidence` e marca a anterior como
  superada (`superseded_by_id`) — nunca sobrescreve no lugar.
- Esta fase **não implementa deduplicação entre fontes diferentes** nem
  correspondência difusa de nome — dois resultados parecidos de fontes
  diferentes (ou até da mesma fonte, sob `place_id`s distintos) permanecem
  como candidatos/empresas distintos até a Fase 2 (Identity Resolution)
  decidir.

## Limites internos (não são limites do Google)

Configuráveis, mas sempre limitados por um teto absoluto que nenhuma
configuração consegue ultrapassar (`ABSOLUTE_MAX_RESULTS=60`,
`ABSOLUTE_MAX_PAGES=3`, em `app/domains/discovery/schemas.py`):

| Parâmetro | Padrão | Propósito |
|---|---|---|
| `max_results` (por busca) | 20 | Teto de resultados persistidos por `SearchRun`. |
| `max_pages` (por busca) | 1 | Teto de chamadas de paginação por `SearchRun`. |
| `discovery_http_connect_timeout_seconds` | 5.0 | Timeout de conexão por chamada. |
| `discovery_http_read_timeout_seconds` | 10.0 | Timeout de leitura por chamada. |
| `discovery_http_max_retries` | 3 | Tentativas extras para erro transitório. |
| `discovery_http_backoff_base_seconds` / `_max_seconds` | 0.5 / 8.0 | Backoff exponencial entre tentativas. |

## Cache

Best-effort, via o mesmo Redis já usado pela fila (nenhum componente
novo). Chave determinística (`provider + página + parâmetros normalizados
da DiscoveryQuery`), TTL configurável
(`DISCOVERY_CACHE_TTL_SECONDS`, padrão 24h). Se o Redis estiver
indisponível — como nesta máquina de desenvolvimento —, toda operação de
cache falha silenciosamente e o Discovery segue sem cache; nunca trava a
busca. Ver `app/domains/discovery/cache.py`.

## Custos

Nenhum preço é fixo no código. `ProviderUsageRecord` registra, por chamada
real: provider, operação, campos solicitados, contagem de resultados e
(quando configurado) custo estimado. `SearchRun.cost_estimate` é a soma
dos registros daquela busca.

```
DISCOVERY_COST_PER_REQUEST=      # vazio = nenhum custo estimado (padrão)
DISCOVERY_COST_CURRENCY=USD
```

Sem esse valor configurado, o sistema ainda assim rastreia **quantas**
chamadas foram feitas e com quais campos — o suficiente para o operador
aplicar o preço real da sua conta do Google Cloud manualmente, sem que o
código precise "saber" esse preço.

## Jobs e execução assíncrona

`DiscoveryJob` (`app/domains/discovery/jobs.py`) segue a abstração `Job`
da Fase 0. `enqueue_or_run_discovery()` tenta enfileirar no Redis (RQ); se
a fila estiver indisponível — o caso desta máquina de desenvolvimento, que
não tem Redis instalado —, executa a mesma lógica de forma síncrona
(reaproveitando a sessão de banco já aberta pela requisição HTTP, quando
chamado por ela) em vez de travar ou derrubar a requisição. Isso é um modo
operacional documentado, não uma substituição do Redis pela arquitetura:
com Redis disponível, o caminho enfileirado é sempre o usado, e um worker
de verdade (`run_discovery_search`, importável por referência de módulo
para o RQ serializar) abre sua própria sessão.

## API HTTP

```
POST /api/discovery/search
GET  /api/discovery/runs/{run_id}
```

`POST` valida o corpo como `DiscoveryQuery`, cria o `SearchRun`, executa
(enfileirado ou síncrono) e devolve o estado resultante com HTTP 202. Sem
`GOOGLE_MAPS_API_KEY` configurada, a resposta ainda é 202 — o `SearchRun`
vem com `status="failed"` e `error_message` explicando a causa; a API
nunca retorna 500 nem trava por falta de credencial.

`GET` devolve o estado atual de uma execução (para o caso enfileirado, que
o operador consulta depois). Um `run_id` desconhecido devolve 404.

## Testes

68 testes cobrem este domínio (ver `backend/tests/discovery/`), 67 deles
na suíte padrão e 1 externo/opcional (ver abaixo):
validação de `DiscoveryQuery`, normalização, o provider Google Places
(com `httpx.MockTransport` — nunca uma chamada real: respostas válidas,
vazias, 400/401/403/429/5xx, timeout, conexão recusada, paginação),
`DiscoveryService` de ponta a ponta com um provider falso (persistência,
idempotência de reprocessamento, falhas controladas, rastreamento de
custo) e a API HTTP. Nenhum teste da suíte padrão depende de rede ou de
uma chave real.

Um teste de integração real e opcional, explicitamente marcado
(`@pytest.mark.external`) e **não incluído na suíte padrão**, existe em
`tests/discovery/test_google_places_live.py`.

### Rodando a suíte padrão

```bash
cd backend
pytest
```

### Teste manual com uma chave real

Depois de configurar `GOOGLE_MAPS_API_KEY` em `backend/.env` com uma chave
sua (nunca no código-fonte):

```bash
cd backend
RUN_EXTERNAL_TESTS=1 GOOGLE_MAPS_API_KEY=sua_chave_aqui pytest -m external tests/discovery/test_google_places_live.py
```

Ou, para testar manualmente pela API com o servidor local rodando:

```bash
curl -X POST http://localhost:8000/api/discovery/search \
  -H "Content-Type: application/json" \
  -d '{"region": "Interlagos", "city": "São Paulo", "category": "restaurantes", "max_results": 5}'
```

## Limitações desta fase

- Só o provider Google Places está implementado; OpenStreetMap e fontes
  comerciais ficam como extensão futura documentada.
- Sem deduplicação entre fontes/registros parecidos (Fase 2).
- Sem decomposição estruturada de endereço (cidade/estado vêm da busca,
  não do resultado individual).
- Preços/cotas reais da API não são validados pelo código — apenas
  rastreados quando configurados manualmente.
- O modo de execução síncrona (sem Redis) não foi testado nesta máquina
  contra uma fila real — apenas o caminho de fallback. Ver
  `docs/development.md`.
