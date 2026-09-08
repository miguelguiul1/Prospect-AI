# Sales Brief — Fase 4

## O que é

O Sales Brief é o **único componente de todo o Prospect AI (Fases 0-4) que
chama um provider de IA**. Ele gera um briefing de prospecção em linguagem
natural para UM prospect, estritamente fundamentado nos dados já existentes
no sistema (`Company`, `Evidence`, `AuditSnapshot`, `WebsiteQuality`,
`OpportunityScore`) — nunca faz nenhuma pesquisa nova, nunca chama um
provider de dados adicional.

## Arquitetura

```
Company -> OpportunityScore mais recente -> AuditSnapshot/WebsiteQuality
        -> Evidence atual (telefone, endereço, website, rating, ...)
        -> BriefingContext -> build_prompt() -> SalesBriefProvider.generate()
        -> validação (SalesBriefContent) -> SalesBrief persistido
```

- `app.domains.briefing.prompt`: constrói o prompt (system + user).
- `app.domains.briefing.providers`: contrato (`SalesBriefProvider`) +
  registro de providers + `AnthropicProvider` (única implementação).
- `app.domains.briefing.schemas`: `SalesBriefContent` — o contrato de saída
  que toda resposta do provider precisa validar.
- `app.domains.briefing.service`: orquestração completa.
- `app.domains.briefing.jobs`: integração com `enqueue_or_run` (mesmo
  padrão de Discovery/Digital Audit).
- `app.domains.briefing.models`: `SalesBrief`.

Isto **NÃO é** um framework de agentes — nenhum CrewAI, AutoGen, LangChain,
LangGraph ou similar foi adicionado. É uma única chamada request/response a
um provider de texto, no mesmo espírito de `DiscoveryProvider` (Fase 1).

## Grounding: nunca inventar fatos

O `system prompt` (`SYSTEM_PROMPT`, constante fixa em
`app.domains.briefing.prompt`) instrui o modelo a:

1. Usar **somente** os dados do bloco de contexto — nunca inventar
   faturamento, número de funcionários, orçamento, tecnologias usadas,
   clientes do prospect, intenção de compra, ou qualquer fato ausente.
2. Declarar explicitamente quando um dado é inconclusivo/não verificado —
   nunca tratar ausência de dado como confirmação de que algo não existe
   (mesmo princípio de `DataState`, Fase 0).
3. Tratar `rating`/`review_count` como sinal de visibilidade pública —
   nunca como faturamento/orçamento/capacidade de compra (mesma regra do
   Opportunity Score).

## Estrutura do briefing

`SalesBriefContent` (Pydantic, `app.domains.briefing.schemas`) exige
exatamente estes campos, todos não vazios:

| Campo | Conteúdo |
|---|---|
| `summary` | Resumo de 1-2 frases do prospect. |
| `opportunity` | Por que este prospect representa oportunidade. |
| `why_this_prospect` | Justificativa ligada aos dados observados. |
| `digital_gaps` | Gaps de presença digital identificados. |
| `suggested_angle` | Ângulo de abordagem comercial sugerido. |
| `talking_points` | Lista de 3 a 5 pontos curtos para a conversa. |
| `risks_and_caveats` | Ressalvas — o que não foi confirmado, o que pode estar desatualizado. |
| `evidence_used` | Lista curta citando os dados efetivamente usados. |

Qualquer resposta que não seja JSON válido, ou que não valide contra este
schema (campo faltando, `talking_points` fora de 3-5, string vazia), é
rejeitada — nunca persistida como sucesso (ver "Falhas" abaixo).

## Segurança: prompt injection

Mesmo princípio de `app.domains.audit.html_signals` (Fase 3): **conteúdo
externo é dado, nunca instrução**. Qualquer valor que vem de `Evidence`/
`WebsiteQuality`/`OpportunityScore` (título de página, meta description,
nome de empresa) pode ter sido escrito por um terceiro, então:

1. É interpolado dentro de um bloco de dados claramente delimitado
   (`<EVIDENCIA_NAO_CONFIAVEL>...</EVIDENCIA_NAO_CONFIAVEL>`), nunca dentro
   do `system prompt`. O `system prompt` é uma constante fixa — nenhum dado
   de `Evidence` é concatenado a ele, sob nenhuma circunstância.
2. O `system prompt` instrui explicitamente o modelo a tratar qualquer
   frase que pareça um comando, encontrada DENTRO do bloco de dados, como
   texto comum coletado de uma fonte externa — nunca como instrução válida.
3. **Neutralização de delimitador**: qualquer ocorrência literal dos
   marcadores `<EVIDENCIA_NAO_CONFIAVEL>`/`</EVIDENCIA_NAO_CONFIAVEL>`
   dentro de um valor de evidência é substituída antes da interpolação
   (`_neutralize`, `app.domains.briefing.prompt`) — sem isso, um valor
   malicioso contendo o próprio marcador de fechamento poderia, em tese,
   "escapar" do bloco de dados. Equivalente, para prompt, da revalidação de
   DNS/IP a cada redirect no SSRF da Fase 3.

Testado em `tests/briefing/test_prompt.py` (prova estrutural — o texto
malicioso nunca alcança o `system prompt` e nunca escapa do bloco de dados)
e em `tests/briefing/test_service.py::
test_prompt_injection_in_evidence_is_inert` (prova de comportamento — uma
evidência com "IGNORE ALL PREVIOUS INSTRUCTIONS..." embutida produz um
briefing normal, gerado a partir do contexto real, nunca um desvio de
comportamento do sistema).

## Provider: por que `httpx` puro, não o SDK `anthropic`

`AnthropicProvider` (`app.domains.briefing.providers.anthropic_provider`)
chama a Messages API pública da Anthropic (`POST /v1/messages`) diretamente
via `httpx`, sem adicionar o SDK oficial `anthropic` como dependência.
Decisão deliberada de dependência mínima, na mesma filosofia das Fases
0-3 (que preferem `httpx`/stdlib a uma biblioteca nova sempre que a chamada
é simples o suficiente — ver `docs/development.md`, "Por que não há
poetry/pipenv"): esta é uma única chamada POST/JSON, sem streaming, sem uso
de ferramentas (tools) e sem multi-turno — o SDK inteiro traria muito mais
superfície do que a Fase 4 precisa. Nenhuma dependência nova foi adicionada
a `requirements.txt` por causa da Fase 4.

Configuração (`.env`, ver `.env.example`): `ANTHROPIC_API_KEY` (sem ela, o
provider fica indisponível de forma controlada — nenhuma chamada é
tentada), `ANTHROPIC_MODEL` (identificador de modelo configurável pelo
operador — o valor default do código não é garantia de disponibilidade;
confira a documentação da Anthropic antes de configurar em produção),
`ANTHROPIC_API_BASE_URL`, timeouts e `ANTHROPIC_MAX_TOKENS`.

## Falhas: nunca um briefing inventado

Toda falha vira `SalesBrief.status=FAILED`, com `error_code`/
`error_message` preenchidos — nunca um briefing parcial ou fabricado, e
nunca um HTTP 500:

| Situação | `error_code` |
|---|---|
| `ANTHROPIC_API_KEY` não configurada | `ProviderUnavailableError` |
| Timeout na chamada | `ProviderTimeoutError` |
| Erro de conexão / credencial rejeitada (4xx) | `ProviderRequestError` |
| Rate limit (429) ou erro do servidor (5xx) | `ProviderTemporaryError` |
| Resposta não é JSON válido, ou não valida contra `SalesBriefContent` | `ProviderInvalidResponseError` |

**Degradação graciosa**: o Opportunity Score é inteiramente independente
do Sales Brief (calculado antes, sem nenhuma dependência de IA) — uma
falha do provider de IA nunca afeta o Opportunity Score, testado
explicitamente em
`tests/briefing/test_service.py::
test_opportunity_score_still_works_when_provider_unavailable` e validado
manualmente fora do pytest com o servidor real rodando sem
`ANTHROPIC_API_KEY` configurada (ver seção "Validação real" no relatório
da Fase 4).

Nenhuma tentativa automática de retry acontece dentro do Sales Brief — uma
chamada de IA já é cara e lenta o suficiente; um erro vira `FAILED`
imediato, nunca um retry silencioso que poderia mascarar instabilidade do
provider.

**Achado real (Prompt 11 — primeira chamada real à Anthropic API deste
projeto)**: apesar da instrução "responda apenas com JSON, sem markdown"
no prompt, o modelo real por vezes envolve a resposta em um bloco de
código Markdown (` ```json ... ``` `) mesmo assim — `json.loads` falharia
com `ProviderInvalidResponseError` sem tratamento. `app.core.ai_text.
strip_markdown_code_fence` (compartilhado com Outreach e a geração de
Prototype) remove esse envoltório antes de parsear, quando presente,
tolerando o comportamento real do provider sem depender só da instrução
do prompt. Testado em
`tests/briefing/test_service.py::test_json_wrapped_in_a_markdown_code_fence_is_parsed_anyway`.

## Custos/uso: nunca inventados

`duration_ms`, `input_tokens` e `output_tokens` só são persistidos quando o
próprio provider os retorna explicitamente na resposta — nunca estimados
ou calculados localmente. Se a API não informar uso de tokens, os campos
ficam `NULL`, nunca um palpite.

## Histórico preservado

Cada chamada a `POST /api/sales-brief/{company_id}` cria uma linha nova em
`sales_briefs` — nunca sobrescreve uma anterior, mesmo em caso de falha
(um `FAILED` também é uma linha histórica válida: "nesta data, com esta
versão do prompt, o provider estava indisponível"). `GET
/api/sales-brief/{company_id}` retorna sempre a mais recente.

O vínculo é com `opportunity_score_id` (não diretamente com
`audit_snapshot_id` nem só com `company_id`): seguir essa referência já
reconstrói exatamente qual versão dos dados (`OpportunityScore.
scoring_version` + a cadeia até o `AuditSnapshot` que o gerou)
fundamentou aquele briefing — não é necessário um campo extra de "versão
de contexto".

## API

```
POST /api/sales-brief/{company_id}   → gera um novo briefing (enfileirado, ou síncrono se a fila estiver indisponível)
GET  /api/sales-brief/{company_id}   → consulta o briefing mais recente
```

`POST` valida precondições de forma síncrona ANTES de enfileirar/executar
(empresa existe, Opportunity Score já calculado) — erros de precondição
retornam `404`/`409` imediatos, nunca um job enfileirado que falharia
silenciosamente depois. A chamada ao provider em si roda através do mesmo
padrão `enqueue_or_run` de Discovery/Digital Audit (faz sentido enfileirar
aqui, ao contrário do Opportunity Score, porque esta chamada é externa e
pode ser lenta).

## Limitações conhecidas

1. **Nenhuma chamada real à API da Anthropic foi feita nesta
   implementação** — não há `ANTHROPIC_API_KEY` disponível neste ambiente
   de desenvolvimento. Toda a suíte de testes usa um provider fake
   injetado (`tests/briefing/test_service.py`) ou `httpx.MockTransport`
   contra o formato documentado da Messages API
   (`tests/briefing/test_providers.py`); a validação manual fora do pytest
   também usou um provider mockado, nunca uma chamada real (ver relatório
   da Fase 4, seção "Validação real"). Antes de usar em produção,
   configure uma chave real e valide manualmente pelo menos uma chamada de
   verdade.
2. **`ANTHROPIC_MODEL` é uma configuração, não uma garantia** — o valor
   default no código (`claude-sonnet-4-5-20250929`) deve ser conferido
   contra a documentação oficial da Anthropic antes de operar em produção;
   modelos são descontinuados/atualizados com o tempo.
3. **Nenhuma sanitização de conteúdo além da neutralização de delimitador**
   é aplicada ao texto de evidência — a defesa contra prompt injection
   depende inteiramente de (a) nunca concatenar dado ao `system prompt` e
   (b) neutralizar o próprio marcador de delimitação; não há, por exemplo,
   um classificador separado de "isto parece uma tentativa de injeção".
   Suficiente para o escopo desta fase (nenhuma ferramenta/ação é exposta
   ao modelo — só geração de texto), mas não uma defesa genérica.
