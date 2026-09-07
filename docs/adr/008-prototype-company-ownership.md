# ADR-008: Ownership de Prototype derivado de Opportunity, não um `owner_id` próprio

**Status**: Aceita (Prompt 10)

## Contexto

`Prototype` (Fase 6) tinha uma coluna `owner_id` (`String`, nunca uma FK)
que nunca foi preenchida nem usada — um placeholder de antes de existir
autenticação real. A Fase 7 trouxe autenticação (JWT) e um modelo de CRM
onde `Opportunity.owner_id` (FK real para `users.id`) já resolve ownership
de forma exclusiva por usuário. `Prototype` continuava sem nenhum vínculo
com `Company`, o que tornava impossível saber para qual empresa um
protótipo foi feito — um bloqueador direto para a Fase 9 (geração de
protótipo por IA), que precisa de contexto de empresa (evidência, Sales
Brief) para gerar algo com sentido.

A pergunta de design: `Prototype` deveria ganhar seu **próprio** `owner_id`
(como `Opportunity` tem), ou deveria derivar acesso de outra entidade?

## Decisão

`Prototype` ganha `company_id` (FK para `companies.id`), e **não** ganha
um `owner_id` próprio. O acesso é derivado exatamente como `Contact` já
funciona (`app.domains.crm.authorization.user_owns_any_opportunity_for_company`):
"este usuário tem uma `Opportunity` para a `Company` deste `Prototype`".

Motivo: um `owner_id` próprio em `Prototype` seria uma segunda fonte de
verdade sobre "quem pode ver isto" que poderia divergir de quem realmente
tem uma `Opportunity` ativa para aquela empresa — exatamente o problema
que `Contact` já evita não tendo seu próprio `owner_id`. Um protótipo é
inerentemente sobre uma empresa (não sobre um usuário), então derivar
ownership da relação usuário↔empresa já existente (`Opportunity`) é mais
consistente do que introduzir um segundo modelo de posse paralelo.

`company_id` é `NULL`-ável no banco (nunca `NOT NULL`) só para preservar
protótipos criados antes desta migration sem inventar uma empresa falsa
para eles — nenhuma criação nova a partir desta fase pode omitir
`company_id` (`PrototypeCreateRequest` o exige; `PrototypeService.create`
verifica que o usuário tem acesso à empresa antes de persistir).

## Consequências

- Criar um `Prototype` exige que o usuário já tenha uma `Opportunity` para
  a empresa — não é possível criar um protótipo "solto" sem contexto
  comercial prévio. Isso é uma restrição deliberada, não um efeito
  colateral: um protótipo sem uma `Opportunity` associada nunca teria como
  ser acessado depois de criado de qualquer forma (a mesma checagem vale
  para leitura/edição/exclusão).
- Protótipos legados (`company_id IS NULL`) ficam permanentemente
  inacessíveis pela API — aceitável porque nenhum ambiente de produção
  real jamais rodou este projeto.
- **Consequência não resolvida nesta fase**: o fluxo de criação do
  frontend (`NewPrototypeDialog`) não tem nenhum seletor de empresa —
  criado como um fluxo standalone na Fase 6, antes deste vínculo existir.
  O botão "Novo protótipo" da página `/prototypes` fica temporariamente
  indisponível até uma fase futura (provavelmente a própria Fase 9)
  adicionar um ponto de entrada com contexto de empresa. Ver
  `docs/prototype-builder.md`.
