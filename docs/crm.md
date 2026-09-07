# CRM + Outreach — Fase 7

## O que é

A Fase 7 transforma o Prospect AI de uma plataforma de inteligência/
prospecção (Fases 0-6, sem autenticação) em uma plataforma que também
permite acompanhar oportunidades comerciais: autenticação real, ownership,
pipeline, contatos, timeline e sugestão de mensagens de outreach por IA
(revisadas por um humano antes de qualquer envio — **nenhum envio
automático existe**).

Implementada em ordem, sem quebrar F0-F6: **F7.1** Auth + Identity, **F7.2**
Ownership + CRM Core (Opportunity/Pipeline), **F7.3** Pipeline, **F7.4**
Contacts/Activities/Timeline, **F7.5** CRM Frontend, **F7.6** Assisted
Outreach + IA, **F7.7** Hardening + Testes.

## Autenticação (F7.1)

Estratégia definida pelo ADR-001 da auditoria F7.0: **JWT próprio**
(`PyJWT` + `bcrypt`), sem provedor de identidade gerenciado externo — mesma
postura de zero-dependência-além-do-necessário do resto do projeto.

- `app.domains.auth.models.User`: `id`, `email` (único), `name`,
  `password_hash` (nunca a senha em texto puro), `is_active`.
- `app.domains.auth.security`: hashing (`bcrypt`) e emissão/validação de
  token (`PyJWT`, `HS256`).
- `app.domains.auth.dependencies.get_current_user`: **único** lugar do
  backend que lê/decodifica o header `Authorization: Bearer <token>` — toda
  rota protegida depende dela (`Depends(get_current_user)`), nunca reparseia
  o token por conta própria.
- Rotas: `POST /api/auth/register`, `POST /api/auth/login` (rate limitado
  por e-mail), `POST /api/auth/logout` (trivial — JWT é stateless, o
  "logout" real é o cliente descartar o token), `GET /api/auth/me`.

No frontend, o token vive em um **cookie httpOnly** (`lib/auth/session.ts`)
— nunca em `localStorage`. `lib/api/client.ts` é o único lugar que lê o
cookie e anexa `Authorization` a cada chamada ao backend; o browser nunca
conversa diretamente com o FastAPI (arquitetura Browser → Next.js → FastAPI
preservada). `src/proxy.ts` (convenção do Next.js 16 — antigo
`middleware.ts`) redireciona para `/login` quando não há cookie de sessão;
essa é só a primeira linha de defesa — a autorização de verdade é sempre
feita pelo backend a cada requisição.

## Ownership e autorização (F7.2)

Modelo desta primeira versão (ADR-003): um único `owner_id` por
`Opportunity`, sem papéis/times. `app.domains.crm.authorization` é o ponto
único de checagem — toda rota que recebe um `{id}` passa por
`get_owned_opportunity_or_404`/`get_owned_activity_or_404`/
`get_accessible_contact_or_404` antes de qualquer leitura/escrita. Sempre
retorna **404** (nunca 403) tanto para "não existe" quanto para "existe mas
não é seu" — evita que um chamador confirme por enumeração que um ID
existe sem ter acesso a ele (mitigação padrão de IDOR).

`Contact` não tem `owner_id` próprio (pertence a uma `Company`, que
continua compartilhada) — o acesso é derivado de "este usuário possui pelo
menos uma `Opportunity` para a empresa deste contato".

## CRM Core (F7.2/F7.3)

```
Company -> Opportunity -> PipelineStage
                        -> Owner (User)
                        -> Contacts
                        -> Activities (timeline)
                        -> Outreach
```

`Opportunity` referencia `Company` só por `company_id` — nunca copia nome/
endereço/telefone/website/categoria. `status` (`OPEN`/`WON`/`LOST`/
`ARCHIVED`) e `stage` (etapa do funil) são conceitos deliberadamente
separados.

8 etapas globais (`pipeline_stages`, migration `0008`): Novo, Qualificado,
Contato realizado, Reunião, Proposta, Negociação, Ganho (`is_won`), Perdido
(`is_lost`). Nenhuma tabela `Pipeline` contêiner (ADR-004) — um único
conjunto implícito é suficiente.

**Idempotência**: `POST /api/crm/opportunities` nunca cria uma segunda
`Opportunity` `OPEN` para a mesma empresa — reforçado por um **índice único
parcial** no banco (`uq_opportunities_company_open`, `WHERE status =
'OPEN'`), não só por uma checagem na aplicação, para resistir a duas
requisições concorrentes.

## Contacts e Activities (F7.4)

`Contact` nunca é criado automaticamente a partir de dados da Discovery —
telefone/site em nível de empresa não são "um contato pessoal válido"
(`source` sempre `manual`/`imported`/`form`, nunca `discovery`).

`Activity` é uma **única tabela** com um campo `type` (`NOTE`, `TASK`,
`CALL`, `MEETING`, `EMAIL`, `WHATSAPP`, `OUTREACH`, `STAGE_CHANGE`,
`OWNERSHIP_CHANGED`, `SYSTEM`) — mesmo padrão de "uma tabela, um campo de
discriminação" já usado em `DedupCandidate` (Fase 2). Mudança de etapa e de
responsável já são `Activity` automáticas; não existe uma tabela separada de
histórico (ADR-005). A timeline de uma `Opportunity` é só uma consulta
ordenada por `created_at`.

## Assisted Outreach + IA (F7.6)

**Nível 1 apenas** (ADR-006, auditoria F7.0): a IA sugere assunto+mensagem,
o vendedor revisa/edita e envia manualmente fora do sistema; só então marca
`SENT_MANUALLY`. **Nenhum envio automático de email/WhatsApp existe.**

```
Opportunity + Contact (opcional) -> Company/Score/Website Quality/Sales Brief
    (via app.domains.companies.queries.get_company_detail, reaproveitado)
    -> OutreachPromptContext -> build_prompt() -> AnthropicProvider.generate()
    -> validação (OutreachContent) -> Outreach persistido (status=DRAFT)
```

Reaproveita o **mesmo** `AnthropicProvider` do Sales Brief (Fase 4) — só
`max_tokens` é diferente (`OUTREACH_MAX_TOKENS`, teto menor que o do
briefing). `generate()` ganhou um parâmetro opcional `max_tokens` (aditivo,
retrocompatível — o Sales Brief não precisa passá-lo).

**Grounding (ADR-007)**: a IA só personaliza a mensagem com nome/cargo de um
`Contact` cujo `validation_status == VERIFIED` — nunca com um contato ainda
não validado por um humano. Mesma técnica de bloco de dados delimitado +
neutralização de marcador do Sales Brief protege contra prompt injection via
Evidence/conteúdo de site. Uma resposta que não valide contra
`OutreachContent` **nunca** é salva como rascunho — a geração falha de forma
controlada (HTTP 502), sem outreach fabricado.

Geração de rascunho é limitada por rate limiting best-effort via Redis
(`OUTREACH_RATE_LIMIT_MAX_PER_DAY`) — mesmo mecanismo do rate limit de
login (`app.core.rate_limit`), falha aberta se o Redis estiver indisponível.

## Variáveis de ambiente novas

Ver `backend/.env.example`, seção "Autenticação (Fase 7)" e "Assisted
Outreach (Fase 7)": `JWT_SECRET_KEY` (**gere um valor real antes de
produção** — o default do código é inseguro de propósito),
`JWT_ALGORITHM`, `JWT_ACCESS_TOKEN_EXPIRE_MINUTES`,
`AUTH_LOGIN_RATE_LIMIT_MAX_ATTEMPTS`, `AUTH_LOGIN_RATE_LIMIT_WINDOW_SECONDS`,
`OUTREACH_RATE_LIMIT_MAX_PER_DAY`, `OUTREACH_MAX_TOKENS`. Reservadas (não
lidas por nenhum código ainda — Nível 2 futuro): `EMAIL_PROVIDER_API_KEY`,
`WHATSAPP_PROVIDER_API_KEY`.

## Migrations

`0007_auth_users`, `0008_crm_core` (pipeline_stages + seed das 8 etapas +
opportunities), `0009_crm_contacts_activities`, `0010_crm_outreach`. Nenhuma
migration anterior (`0001`-`0006`) foi alterada.

## Testes

`backend/tests/{auth,crm,outreach}/` — unit (serviço), API (fluxo real via
`client`, registro→login→uso do token) e autorização/IDOR dedicada
(`tests/crm/test_authorization.py`: usuário A nunca acessa/modifica dado de
usuário B, sempre 404). `frontend/src/components/{auth,crm}/*.test.tsx` —
formulário de login/registro, badges, seletor de etapa, ações de fechar/
reabrir, timeline, contatos, outreach (incluindo o caminho de falha de
geração e o filtro de contatos não verificados).

## O que fica explicitamente fora deste F7

Envio automático de e-mail/WhatsApp, integração com provedor real de envio
(Nível 2), automação/sequências (Nível 3), papéis/times (RBAC além de
owner único), múltiplos pipelines nomeados, `Lead` como entidade separada
de `Opportunity`, scraping ou automação de LinkedIn/redes sociais. Ver a
auditoria F7.0 (histórico de sessão) para a justificativa de cada decisão.

## Limitações conhecidas

PostgreSQL/Redis reais não foram validados nesta máquina de desenvolvimento
(mesma limitação já documentada desde a Fase 0) — todo teste e a validação
manual desta fase rodaram contra SQLite e sem Redis real (rate limiting
testado no modo "falha aberta"). O código não assume nenhum dos dois
disponível, mas **produção exige ambos configurados de verdade**.
