# Geração de Prototype por IA — Fase 9 / Prompt 11

## O que é

A primeira geração automática de um protótipo de site por IA, a partir de
dados reais de uma empresa: `Company` → Context Builder → prompt →
provider de IA → árvore de componentes (JSON) → validação → persistida
como `Prototype.components`. Uma única chamada request/response, nunca
multi-agente — confirmado deliberadamente fora de escopo por esta fase.

Constrói sobre o que já existia: o catálogo fechado de componentes e a
validação estrutural do Prototype Builder (Fase 6), o vínculo
`Prototype`↔`Company` e a autorização derivada de `Opportunity` (Prompt
10), e o mesmo padrão de provider/prompt/grounding já usado pelo Sales
Brief (Fase 4) e Assisted Outreach (Fase 7).

## Grounding: a regra mais importante desta fase

**O gerador nunca pode inventar um fato sobre a empresa.** Isso é
aplicado em três camadas, não uma só:

1. **Classificação de confiança no Context Builder** — todo dado é
   FACT/SIGNAL/UNKNOWN/INFERENCE (ver seção abaixo), nunca um valor
   "pelado" sem indicação de certeza.
2. **Instrução explícita no prompt** — o modelo é instruído a nunca
   escrever um fato específico (endereço, telefone, preço, produto) que
   não esteja marcado FACT/SIGNAL no contexto; copy genérico de UX é
   aceitável mesmo sem estar no contexto.
3. **Heurística de grounding pós-geração** — um scan por regex sinaliza
   texto gerado que parece um fato numérico (telefone/CNPJ/preço) sem
   correspondência no contexto conhecido. Nunca bloqueia, só avisa (ver
   "Validação" abaixo).

Nenhuma das três é uma garantia absoluta — são defesas em camadas, como
toda defesa contra alucinação de LLM já é neste projeto (mesma postura de
`docs/sales-brief.md`).

## Context Builder

`app/domains/prototypes/context.py` — `PrototypeContextBuilder.build(company_id)`
monta um `PrototypeContext` a partir de `Company`, `Evidence` (Fases
0/1/3), `AuditSnapshot`/`site_state` (Fase 3), `OpportunityScore` (Fase
4), e o `SalesBrief` mais recente com status `completed` (Fase 4) — nunca
o HTML bruto de uma página, só os sinais já extraídos.

**Confiança de cada campo**:

| Nível | Significado | Exemplo |
|---|---|---|
| `FACT` | Confirmado | Nome da empresa; `Evidence` com `state=CONFIRMED` + `confidence=HIGH` |
| `SIGNAL` | Indício público, não uma certeza | `Evidence` confirmada com confiança MEDIUM/LOW; qualquer `DataState` de auditoria diferente de CONFIRMED (uma checagem foi tentada e não confirmou — isso é informação, não ausência dela) |
| `UNKNOWN` | Não observado — nunca omitido, sempre explícito | Nenhuma `Evidence` para aquele campo |
| `INFERENCE` | Inferência já calculada por outro sistema, rotulada como tal | `Evidence.method=INFERENCE`; `recommended_product` do Opportunity Score; conteúdo do Sales Brief (ele mesmo é saída de IA, nunca fato observado) |

**Campo obrigatório vs. opcional**: só `company_name` é tecnicamente
obrigatório (`Company.canonical_name` é `NOT NULL`). Isso sozinho não
basta — um contexto com nome mas zero `Evidence` e zero `AuditSnapshot`
daria ao Generation Engine nada para fundamentar o protótipo além do
nome. Por isso a construção falha explicitamente
(`InsufficientContextError`) quando a empresa não tem nenhuma `Evidence`
nem nenhum `AuditSnapshot` — o mínimo de material real. Todo outro campo
vira `UNKNOWN` quando ausente, nunca lança erro nem é omitido.

`freshness` (data da evidência mais antiga usada, não a mais recente —
sinaliza o pior caso de desatualização) e `provenance` (`ContextField.source`,
de qual coluna/domínio cada valor veio) viram o `ContextSnapshot`
imutável de cada geração.

## Generation Engine

`app/domains/prototypes/generation/` — mesma estrutura de
`app/domains/briefing/providers/`, reaproveitando o MESMO
`SalesBriefProvider`/`AnthropicProvider`/`ProviderResponse` (Fase 4) em
vez de duplicar uma terceira implementação de chamada HTTP à Anthropic —
só o prompt e a validação são específicos deste domínio.

```
PrototypeContext -> build_prompt() -> provider.generate() -> JSON -> validação -> persistência
```

**Prompt** (`generation/prompt.py`): mesma técnica de neutralização de
delimitador de `briefing/prompt.py` — todo dado do contexto é interpolado
dentro de um bloco delimitado (`<CONTEXTO_NAO_CONFIAVEL>`...`</...>`),
nunca no system prompt; ocorrências literais do marcador dentro de um
valor são neutralizadas antes da interpolação, para que um valor malicioso
não consiga "fechar" o bloco prematuramente. Testado explicitamente
injetando texto do tipo "ignore instruções anteriores" em um campo de
contexto (`tests/prototypes/test_generation_prompt.py`) — tratado sempre
como dado inerte.

O modelo é instruído a responder **exclusivamente** com
`{"components": [...]}`, usando só o catálogo fechado (`container,
section, row, column, text, heading, button, image, input, textarea,
card, divider`) — nunca HTML/CSS/JS/Markdown. Sem imagem real conhecida
no contexto, todo componente `image` deve usar `props.placeholder = true`,
nunca uma URL inventada.

## Validação do artefato gerado

`app/domains/prototypes/generation/validation.py`, quatro camadas, a
primeira falha interrompe as seguintes:

1. **Schema/catálogo** — reaproveita `validate_component_tree`
   (`prototypes/schemas.py`, Fase 6) sem duplicar: catálogo fechado,
   ciclos, `parent_id` pendurado, contagem/profundidade máximas, IDs
   duplicados. Puramente estrutural — nunca olha semântica de `props`.
2. **Segurança de URL** — props `src`/`href`/`url`/`link` (os únicos
   nomes usados pelo catálogo hoje, mais os dois últimos por precaução,
   já que `props` não é validado por chave) só aceitam
   `http://`/`https://`/caminho relativo/vazio, nunca `javascript:`,
   `data:`, `file:`, `vbscript:`. Testado forçando o
   `FakeGenerationProvider` a devolver uma URL `javascript:` — rejeitada
   antes de qualquer persistência.
3. **Props obrigatórias por tipo** (`MissingRequiredPropError`, adicionada
   depois do achado real descrito abaixo) — `text`/`heading`/`button`
   exigem `props.content` preenchido (string não vazia). Fecha o gap
   entre "estruturalmente válido" e "renderiza de verdade".
4. **Grounding heurístico** (`find_grounding_warnings`) — regex por
   telefone/CNPJ/preço no texto gerado, sem correspondência no contexto
   conhecido. Nunca bloqueia — os avisos ficam em
   `GenerationRun.grounding_warnings`, para revisão humana.

Qualquer falha nas camadas 1-3 termina em `GenerationRun.status=FAILED`
com o motivo registrado — nunca um protótipo vazio, nunca um retry
silencioso.

## Validação contra a API real (Prompt 11)

Várias chamadas reais à Anthropic API foram feitas nesta sessão (com
autorização explícita e uma `ANTHROPIC_API_KEY` real fornecida pelo
usuário), contra uma empresa com Digital Audit real (HTTP GET real contra
`https://example.com`) e Sales Brief real. As duas primeiras tentativas
falharam por saldo insuficiente na conta (custo zero, nenhum token
processado); depois de crédito adicionado, o pipeline completo (Digital
Audit → Opportunity Score → Sales Brief → Geração de Protótipo) foi
rodado do zero mais duas vezes, revelando dois achados reais que nenhum
teste com `FakeGenerationProvider` jamais teria revelado:

1. **JSON envolvido em markdown**: apesar da instrução explícita "sem
   markdown", o modelo real ocasionalmente envolve a resposta em
   ` ```json ... ``` `. Corrigido com `app.core.ai_text.
   strip_markdown_code_fence` (compartilhado com Sales Brief e Outreach —
   os três domínios tinham o mesmo gap, nunca testados contra a API real
   antes desta fase).
2. **Chave de prop errada**: o modelo usou `props.text` em vez de
   `props.content` para `heading`/`button` — estruturalmente válido,
   mas a interface real só lê `content`, então o texto gerado seria
   silenciosamente descartado (substituído pelo placeholder padrão do
   Builder). Corrigido em duas camadas: o prompt agora especifica os
   nomes exatos de prop por tipo (espelhando `COMPONENT_REGISTRY` do
   frontend), e `MissingRequiredPropError` (camada 3 acima) é a rede de
   segurança estrutural caso o modelo erre de novo — nunca depende só do
   prompt "pedir certo". Ver `docs/adr/013-per-component-type-prop-schema.md`
   para a decisão de escopo (correção mínima agora vs. um schema completo
   por tipo de componente, adiado até um segundo gap real aparecer).

**Confirmado com uma segunda chamada real, após as duas correções**: a
geração sucedeu, com `props.content` corretamente preenchido nos
componentes de texto observados diretamente na resposta (`hero-heading`:
"Example Domain", `hero-cta`: "Solicitar Auditoria Gratuita",
`contact-heading`: "Fale Conosco") — nenhum `MissingRequiredPropError`
levantado, confirmando que a árvore gerada desta vez tinha conteúdo real
em todo componente de texto (o próprio mecanismo de validação garante
isso: um `props.content` ausente teria interrompido a geração inteira).

**Custo real das chamadas desta validação**: as duas primeiras tentativas
falharam por saldo insuficiente na conta, antes de qualquer token ser
processado — custo zero, confirmado. As tentativas seguintes (a que
revelou o markdown envolvendo o JSON, e a que revelou a chave de prop
errada) **tiveram a chamada HTTP concluída com sucesso pelo provider antes
de falhar no parsing/validação do conteúdo** — ou seja, muito provavelmente
foram cobradas normalmente, mesmo tendo terminado como `GenerationRun.
status=FAILED`. Um achado adicional desta mesma validação: até este ponto
da sessão, `PrototypeGenerationService._fail()` não capturava
`input_tokens`/`output_tokens`/`duration_ms` nesse tipo de falha (só no
caminho de sucesso), então o custo real dessas chamadas específicas nunca
chegou a ficar registrado — uma violação do próprio objetivo de
rastreamento de custo do F8 ("identificar toda operação que chama IA:
tokens, custo"). Corrigido nesta mesma sessão: `_fail()` agora recebe e
persiste `input_tokens`/`output_tokens`/`duration_ms` sempre que a
resposta do provider chegou a existir, mesmo em falha — mas os valores
exatos das chamadas que motivaram essa correção não foram recuperados
retroativamente (o registro já tinha sido persistido sem eles). A
chamada final de confirmação (depois de ambas as correções), essa sim com
os números completos capturados: Sales Brief ≈ 968 tokens de entrada /
910 de saída; Prototype Generation ≈ 1.373 / 2.678 — nenhum
`grounding_warning`, `GenerationRun.status=SUCCEEDED`.

## `GenerationRun` + `ContextSnapshot`

`app/domains/prototypes/models.py` — histórico preservado, mesmo padrão
de `SalesBrief`/`AuditSnapshot`: cada execução é uma linha nova.

- **`GenerationRun`**: `status` (`pending`/`succeeded`/`failed`),
  `provider`, `model`, `prompt_version`, `context_version`,
  `input_tokens`/`output_tokens` (só quando o provider os informa, nunca
  estimados), `error_code`/`error_message` (dois campos, não um `error`
  único — ajuste deliberado sobre a sugestão original, para consistência
  com `SalesBrief` e para que o motivo seja consultável
  programaticamente), `grounding_warnings`, `created_at`/`completed_at`.
- **`ContextSnapshot`**: o `PrototypeContext` inteiro serializado
  (`PrototypeContext.to_dict()`), vinculado 1:1 a um `GenerationRun`,
  imutável — persistido mesmo em falhas onde o contexto chegou a ser
  construído (permite diagnosticar "o contexto era bom, foi só o
  provider que falhou" vs. "o contexto já era pobre demais").

Migration `0012_prototype_generation` — duas tabelas novas, nenhuma
alteração em tabela existente; `upgrade`/`downgrade` testados de verdade
(`tests/test_migrations_roundtrip.py`).

**Sem `PrototypeVersion` nesta fase** — decisão explícita, ver
`docs/adr/012-no-prototype-version-yet.md`.

## API

```
POST /api/prototypes/{id}/generate                        → dispara a geração (202)
GET  /api/prototypes/{id}/generations/{generation_id}      → consulta o estado de uma geração
```

Nenhum outro endpoint da auditoria original (`/refine`, `/versions`) foi
implementado — pertencem à próxima fase (Refinamento + Versionamento).

**Síncrono ou assíncrono?** A geração é sempre criada via
`PrototypeGenerationService.start()` (síncrono, cria o `GenerationRun` em
`PENDING` e retorna imediatamente) e depois processada por
`enqueue_or_run_prototype_generation()` — mesmo padrão de
`discovery`/`audit`/`briefing` desde a Fase 8.2: tenta enfileirar via RQ
(fila `prototype_generation`, adicionada a `app.worker.DEFAULT_QUEUES`);
sem Redis (o caso desta máquina), executa a chamada real de forma
síncrona no mesmo processo, ANTES de a resposta HTTP ser enviada. O
contrato da API (`GET /generations/{id}` para consultar o resultado) já é
o certo para quando Redis + um worker real existirem — sem reescrever
nada depois, mesma lição da Fase 8.2 aplicada desde o início desta vez.

**Autorização**: mesma regra de qualquer outra rota de `Prototype`
(Prompt 10) — só quem tem `Opportunity` para a empresa.

**No máximo uma geração em andamento por `Prototype`**: `start()` rejeita
(`409 generation_in_progress`) se já existe um `GenerationRun` em
`PENDING` para o mesmo `Prototype` — checagem síncrona, não uma
constraint de banco (o estado `PENDING` é transitório por natureza).

## Cost control

- `Settings.prototype_generation_max_tokens` (4000, maior que
  Outreach/Sales Brief — uma árvore de até ~30 componentes ocupa mais
  tokens de saída que uma mensagem curta ou um briefing).
- `Settings.prototype_generation_rate_limit_max_per_day` (10, por
  `prototype_id`, política `fail_closed` — mesmo motivo de Sales
  Brief/Outreach: custo financeiro direto).
- Sem retry automático — mesma decisão de cada domínio que chama IA
  neste projeto: um retry de job inteiro poderia duplicar uma chamada
  paga à Anthropic.

## Observabilidade

Reaproveita `app/core/metrics.py` (Fase 8.6): `ai_requests_total{domain="prototype_generation",status}`,
`ai_tokens_total{domain="prototype_generation",direction}`. Logs
(`prototype_generation_succeeded`/`_failed`) carregam `generation_id`,
`prototype_id`, `company_id`, `provider`, `model`, contagem de
componentes, contagem de avisos de grounding — nunca a API key, nunca o
conteúdo bruto do prompt/resposta.

## Frontend

Fecha a lacuna identificada no relatório do Prompt 10 (o formulário "Novo
protótipo" standalone não tinha seletor de empresa): a partir da página
de detalhe do prospect (`/prospects/[companyId]`), a seção "Protótipo"
(`components/prospect-detail/prototype-section.tsx`) oferece um botão
"Gerar Protótipo" — mesmo componente `ActionButton` já usado por "Gerar
Sales Brief". `generatePrototypeAction`
(`app/prospects/[companyId]/actions.ts`) cria o `Prototype` já vinculado
à empresa (nome genérico, "Novo protótipo" — editável depois no Builder,
evita um campo extra só para isto), dispara a geração, e redireciona para
o Builder já populado ao terminar. Se a geração falhar (ex.: contexto
insuficiente), a action nunca redireciona para um Builder vazio
disfarçando a falha — devolve o erro real na própria página do prospect.

Só oferecido quando a empresa já tem uma Opportunity (mesma pré-condição
de acesso da autorização de backend) — sem isso, geração sempre falharia
com 404.

**Não implementado** (próxima fase): chat de refinamento, tela de
histórico de gerações, qualquer UX além de disparar uma geração e ver o
resultado.

## Limitações conhecidas

1. Redis/worker real nunca observados nesta sessão (mesma limitação de
   toda fila do projeto desde a Fase 8) — o caminho `queued` de
   `enqueue_or_run_prototype_generation` é validado só com `fakeredis`.
2. Nenhuma chamada real à Anthropic foi feita durante o desenvolvimento
   desta fase — todo teste usa `FakeGenerationProvider`. Ver relatório
   final do Prompt 11 para se/quando uma chamada real foi autorizada e
   executada.
3. A heurística de grounding (regex de telefone/CNPJ/preço) é
   propositalmente simples — não é NLP, não entende sinônimos ou
   paráfrases de um fato inventado. Primeira linha de defesa, nunca uma
   garantia.
4. Sem versionamento/refinamento — ver ADR-012.
