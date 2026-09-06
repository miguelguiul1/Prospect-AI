# Digital Audit + Website Quality Score — Fase 3

> Digital Audit verifica se uma empresa tem um website próprio acessível e
> avalia a qualidade técnica do que encontrar. Ele não decide oportunidade
> comercial, não gera briefing e não prioriza nada — isso é Opportunity
> Score e Sales Brief (Fase 4, ainda não implementados).

## Objetivo

Responder, para uma `Company` já descoberta (Fase 1) e com identidade
resolvida (Fase 2): "esta empresa tem um site próprio, ele está acessível,
e quão boa é essa presença digital?" — de forma explicável, segura e
reprodutível.

## Fluxo

```
Company
   │
   ▼
select_website_candidate()        ── lê Evidence existente, nunca descobre um site novo
   │
   ├─ nenhum candidato confiável ──► site_state = NOT_DETECTED  (fim, sem rede)
   ├─ candidatos conflitantes ─────► site_state = INCONCLUSIVE  (fim, sem rede)
   │
   ▼ (candidato único e confiável)
validate_url_is_safe()             ── SSRF: esquema, credenciais, DNS/IP
   │
   ├─ bloqueado ────────────────────► site_state = NOT_CHECKED  (decisão de segurança)
   │
   ▼ (seguro)
fetch_safely()                      ── timeout, limite de redirects, limite de tamanho
   │
   ├─ falha de rede/timeout ────────► site_state = INACCESSIBLE
   │
   ▼ (respondeu, qualquer status HTTP)
extract_html_signals()              ── só se content-type for HTML
   │
   ▼
Evidence (append-only) + AuditSnapshot + WebsiteQuality
   site_state = CONFIRMED
```

Cada estágio é um módulo isolado em `app/domains/audit/`:
`website_candidate.py`, `ssrf.py`, `http_client.py`, `html_signals.py`,
`scoring.py`, `service.py` (orquestra), `jobs.py` (fila). Nenhum agente de
IA participa — a auditoria é inteiramente determinística; sinais técnicos
básicos não precisam de IA para serem detectados.

## Dois conceitos de estado, nunca confundidos

- **`AuditStatus`** (`pending`/`running`/`completed`/`failed`) — descreve
  se o PROCESSO da auditoria rodou com sucesso. Um site inacessível,
  ambíguo ou bloqueado por SSRF é um resultado **válido**:
  `status=completed` mesmo assim. `failed` fica só para erros
  verdadeiramente inesperados do próprio processo (ex.: um bug), nunca
  para "o site não respondeu".
- **`DataState`** (reaproveitado do Evidence Layer da Fase 0 — não
  duplicamos um enum novo) — descreve o que foi ENCONTRADO:

  | Estado | Quando |
  |---|---|
  | `confirmed` | O candidato respondeu (qualquer status HTTP, após redirects válidos). |
  | `not_detected` | Não há evidência de site próprio (nenhuma, ou só redes sociais/agregadores). |
  | `inconclusive` | Fontes diferentes reportaram hostnames de site oficial diferentes. |
  | `inaccessible` | Havia um candidato, mas a rede falhou (timeout, conexão recusada, DNS). |
  | `not_checked` | O candidato foi bloqueado pela validação de SSRF — uma decisão de segurança, não uma falha de rede. |

  "Não encontrado" nunca vira "não existe": cada estado acima é distinto e
  nunca colapsado nos outros.

## Website Detection

`select_website_candidate` (`app/domains/audit/website_candidate.py`) lê o
campo `website` do `Evidence` já existente da empresa (produzido por
Discovery/Identity Resolution) — o Digital Audit nunca descobre um site
novo, só audita o que já foi observado. Reaproveita `is_trusted_website`
(promovido de `identity.matching` para `discovery.normalization` nesta
fase — ver "Refatoração" abaixo) para nunca tratar Instagram/Facebook/
TikTok/WhatsApp/Linktree/marketplaces/mapas como website oficial.

Quando as últimas observações do campo `website` (até 5, de fontes
diferentes) apontam para hostnames de site oficial diferentes, o candidato
é `AMBIGUOUS` → `site_state=inconclusive`, nunca uma escolha arbitrária.

## Segurança: proteção contra SSRF

Requisito crítico desta fase (`app/domains/audit/ssrf.py`). Antes de
qualquer conexão — a URL inicial e **cada redirecionamento** (nunca só a
primeira) — validamos:

- esquema (só `http`/`https`);
- ausência de credenciais embutidas na URL;
- o(s) endereço(s) IP resolvido(s) do hostname, rejeitando:
  loopback, `0.0.0.0`, RFC1918 (redes privadas), link-local (inclui o
  endpoint de metadata de nuvem `169.254.169.254`), multicast, reservado,
  não especificado, CGNAT, e as faixas de teste/benchmarking (TEST-NET-1/
  2/3, RFC 2544) — checado tanto via as properties do próprio
  `ipaddress` do Python quanto por uma lista explícita adicional (defesa
  em profundidade).

`app/domains/audit/http_client.py` nunca segue redirect automaticamente
(`follow_redirects=False`) — cada hop é revalidado manualmente. Limite de
redirecionamentos (`AUDIT_HTTP_MAX_REDIRECTS`), timeout obrigatório
(connect/read separados) e limite de tamanho de resposta (leitura em
streaming, interrompida — não rejeitada — ao exceder o limite) são todos
configuráveis. Nunca há retry infinito (`AUDIT_HTTP_MAX_RETRIES`, só para
timeout/conexão — nunca para 4xx/5xx, que são respostas válidas do
servidor). Um `User-Agent` identificável é sempre enviado.

**Limitação conhecida e documentada, não escondida:** a validação de
SSRF acontece ANTES de cada requisição, mas a conexão em si é feita pelo
hostname (não por um IP já fixado/"pinned"). Isso deixa uma janela teórica
de *DNS rebinding* entre a validação e a conexão real. Fechar essa janela
por completo exigiria fixar a conexão TCP ao IP validado (reescrevendo a
URL para o IP e ajustando SNI/Host manualmente) — não implementado nesta
fase. O modelo de ameaça aqui (websites que o próprio Discovery já
encontrou como candidatos de empresas reais) é bem mais brando do que
aceitar URL arbitrária de um usuário anônimo, mas a lacuna é real e fica
registrada para endurecimento futuro.

**Conteúdo de terceiro nunca é instrução.** `html_signals.py` usa
`html.parser.HTMLParser` (biblioteca padrão) — nunca executa JavaScript,
nunca interpreta CSS, nunca segue `<script>`/`<iframe>`. Conteúdo dentro de
`<script>`/`<style>` é explicitamente ignorado na extração de texto (nunca
conta como sinal de contato, nunca é "obedecido"). Nenhum conteúdo
auditado chega a um LLM nesta fase — não há agente de IA no Digital
Audit — mas o princípio já fica estabelecido no código para quando uma
fase futura precisar sintetizar esse conteúdo.

## Evidence Layer

Cada auditoria bem-sucedida (`site_state=confirmed`) grava:

| Campo | Método | Confiança |
|---|---|---|
| `website_accessible` | `structured_field` | `high` — fato direto da resposta HTTP |
| `website_https` | `structured_field` | `high` |
| `website_status_code` | `structured_field` | `high` |
| `website_title` | `heuristic_match` | `medium` — extraído do HTML |
| `website_meta_description` | `heuristic_match` | `medium` |
| `website_contact_available` | `heuristic_match` | `medium` |
| `website_social_links` | `heuristic_match` | `medium` |

Reaproveita o padrão append-only já usado pelo Discovery desde a Fase 1
(`app.domains.evidence.queries.upsert_evidence`, uma versão generalizada
de `discovery.persistence._upsert_evidence` que aceita `state`/
`audit_snapshot_id` variáveis): um valor que não mudou desde a última
observação não gera uma linha nova; um valor que mudou gera uma nova linha
e marca a antiga como superada. Cada `Evidence` de auditoria carrega
`audit_snapshot_id`, ligando-a à execução específica que a produziu.

**Nem todo sinal técnico vira `Evidence`.** Só os que são individualmente
relevantes/auditáveis ao longo do tempo (acima). O dump completo dos ~20
sinais técnicos (contagem de headings, proporção de alt text, tempo de
resposta, etc.) fica em `WebsiteQuality.signals` — um blob versionado por
`AuditSnapshot`, não uma série histórica por campo. Ver
`docs/data-model.md`.

## `AuditSnapshot`: histórico, não um registro mutável

Cada execução cria um `AuditSnapshot` novo — nunca sobrescreve o anterior.
Isso é o que permite responder no futuro: "como estava o website dessa
empresa quando ela foi prospectada?" `run_id` correlaciona a execução nos
logs; `website_url`, `site_state`, `status`, `started_at`/`finished_at` e
`error_code`/`error_message` descrevem o que aconteceu; `website_quality`
(1:1) guarda o score, quando houver.

## Website Quality Score

Metodologia completa (pesos, fórmulas, justificativa) documentada como
docstring de `app/domains/audit/scoring.py` — resumo:

Cinco dimensões (0-100 cada), combinadas por média ponderada: **Segurança**
(25% — HTTPS presente ou não, binário), **SEO técnico** (20% — title/meta
description/canonical/language/robots), **Conteúdo** (20% — estrutura de
headings, informação de contato, links sociais), **UX/Mobile** (20% —
viewport, navegação, formulário) e **Aspectos técnicos** (15% — tempo de
resposta de uma única requisição, content-type, truncamento — nunca
Lighthouse/Core Web Vitals de verdade, porque não os executamos).

**Reprodutível por construção**: `compute_website_quality` é uma função
pura — os mesmos sinais sempre produzem o mesmo score. Nenhuma IA decide
o número.

**Sem score quando o site não está confirmado.** `site_state != confirmed`
→ `score=None`, nunca `0`. Um site inacessível não é "avaliado como ruim"
— é "não avaliável", com o motivo em `limitations`.

**`components`, `signals`, `confidence` e `limitations`** ficam todos
persistidos junto do score (`website_quality_snapshots`), para que o
número nunca apareça desacompanhado do porquê.

Os pesos são uma hipótese inicial documentada, não um resultado de dados
reais — no mesmo espírito dos limiares de similaridade da Fase 2.

## Refatoração: `is_trusted_website` promovido para `discovery.normalization`

Antes da Fase 3, `is_trusted_website`/`UNTRUSTED_WEBSITE_DOMAINS` viviam só
em `app.domains.identity.matching` (Fase 2). Como o Digital Audit precisa
exatamente da mesma regra (site próprio vs. rede social/agregador),
promovemos os dois para `app.domains.discovery.normalization` — módulo do
qual tanto `identity` quanto `audit` já dependem para outras normalizações
— e `identity.matching` passou a reexportar de lá, para não quebrar quem
já importava daquele caminho. Mesma lógica de dedução aplicada em
`app.domains.evidence.queries.upsert_evidence`, generalizado a partir do
`_upsert_evidence` privado do Discovery (que permanece como estava, sem
alteração, evitando qualquer risco de regressão na Fase 1).

## API

```
POST /api/audit/{company_id}   → cria e executa uma auditoria (enfileirada, ou síncrona por fallback)
GET  /api/audit/{company_id}   → consulta a auditoria mais recente da empresa
```

Nenhuma operação destrutiva/administrativa exposta — mesma postura das
Fases 1/2 (sem autenticação implementada ainda).

## Jobs e execução assíncrona

Mesmo padrão de `app.domains.discovery.jobs` (Fase 1): `DigitalAuditJob` +
`enqueue_or_run_audit`, com fallback síncrono documentado quando o Redis
está indisponível (o caso desta máquina de desenvolvimento). Redis/RQ
continuam sendo a arquitetura oficial — não removidos, não substituídos.

## Limites configuráveis

| Variável | Padrão | Papel |
|---|---|---|
| `AUDIT_HTTP_CONNECT_TIMEOUT_SECONDS` | 5.0 | Timeout de conexão. |
| `AUDIT_HTTP_READ_TIMEOUT_SECONDS` | 10.0 | Timeout de leitura. |
| `AUDIT_HTTP_MAX_RETRIES` | 1 | Só para timeout/conexão recusada. |
| `AUDIT_HTTP_MAX_REDIRECTS` | 5 | Nosso limite, não do site. |
| `AUDIT_HTTP_MAX_RESPONSE_BYTES` | 2.000.000 (2 MB) | Resposta truncada, não rejeitada, além disso. |
| `AUDIT_HTTP_USER_AGENT` | `ProspectAI-DigitalAudit/1.0` | Identificação — nunca finge ser um navegador. |

## Dependências

**Nenhuma dependência nova foi adicionada nesta fase.** `httpx` (Fase 1) já
cobre a busca HTTP; `ipaddress`/`socket`/`html.parser` são bibliotecas
padrão do Python, suficientes para validação de SSRF e extração de sinais
HTML sem introduzir BeautifulSoup/lxml (superfície de ataque/dependência
desnecessária para o que esta fase pede) nem um navegador automatizado.

## Limitações desta fase

- Sem "IP pinning" contra DNS rebinding (ver seção Segurança acima).
- Sem crawling: só a página inicial do candidato é analisada — links não
  são seguidos.
- Sinais de "performance" são grosseiros (uma medição de tempo de resposta
  de uma única requisição) — não são Lighthouse/Core Web Vitals.
- Pesos do Website Quality Score são uma hipótese inicial, não calibrados
  com dados reais.
- Certificado TLS: não há verificação/relato granular de validade — uma
  falha de TLS simplesmente faz a requisição falhar (`inaccessible`),
  nunca contornamos a verificação padrão do `httpx`.
- O caminho enfileirado (RQ/Redis) segue não validado com um worker real
  nesta máquina — mesma limitação herdada das Fases 1/2.

## Testes

102 testes cobrem este domínio (`backend/tests/audit/`): SSRF (28 —
esquemas, IPs/redes bloqueadas, resolução de DNS, redirecionamento para
IP privado), cliente HTTP (13 — redirects, limites, erros, retry, 4xx/5xx
não são exceção), extração de HTML (16 — inclusive que `<script>` nunca
vira sinal/instrução), Website Quality Score (22 — todas as dimensões,
determinismo, ausência de score quando inacessível), seleção de candidato
(6), o serviço fim-a-fim (12 — incluindo idempotência do Evidence) e a API
(5). Nenhum usa rede real.

## Como rodar

```bash
cd backend
pytest tests/audit -v
```

## Como auditar uma empresa localmente

Com o backend no ar e uma `Company` que já tenha uma `Evidence` de
`website` (produzida por uma busca de Discovery real ou inserida
manualmente):

```bash
curl -X POST http://localhost:8000/api/audit/<company_id>
curl http://localhost:8000/api/audit/<company_id>
```

Validado nesta implementação com `https://example.com` — o domínio
reservado pela IANA exatamente para esse tipo de teste (leve, estável,
nunca uma auditoria agressiva contra um site de terceiro real).
