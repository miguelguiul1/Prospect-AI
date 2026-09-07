# ADR-010: Não implementar rotação de `JWT_SECRET_KEY` com múltiplas chaves (`kid`) agora

**Status**: Aceita — decisão de NÃO implementar, com gatilho de reconsideração (Prompt 10, seção 2.2)

## Contexto

Hoje `JWT_SECRET_KEY` é um único segredo simétrico (HS256). Trocar esse
valor invalida instantaneamente todas as sessões ativas — não há como
rotacionar o segredo sem derrubar todo mundo que estiver logado. O
relatório final da Fase 8 listou isto como um risco remanescente. A
alternativa considerada: um header `kid` (key id) no JWT, com suporte a
múltiplas chaves válidas simultaneamente (uma nova para assinar, as
antigas ainda aceitas para validar por um período de transição) — o
padrão usado por provedores de identidade reais (Auth0, Firebase, etc.).

## Decisão

**Não implementar agora.** Motivos:

1. **Nenhuma política de rotação existe.** Rotação programada só faz
   sentido quando há uma cadência definida (ex.: a cada 90 dias) ou um
   gatilho operacional real — nenhum dos dois existe neste projeto hoje.
   Implementar o mecanismo sem a política que o motivaria é
   over-engineering: código para um cenário hipotético, não um requisito
   real (ver `AGENTS.md`/instruções do projeto: "não implemente features
   além do que a tarefa exige").
2. **Instância única, sem produção real.** O benefício de rotação sem
   downtime (não derrubar sessões de usuários reais em produção) só se
   materializa quando existe uma base de usuários reais logados — que não
   existe ainda (nenhum ambiente de produção jamais rodou este projeto).
3. **O mecanismo de emergência já existe, só que com um custo aceitável
   hoje**: se `JWT_SECRET_KEY` for comprometido, a resposta correta AINDA
   é trocá-lo imediatamente (ver runbook, "Secret compromised", no
   relatório final da Fase 8) — forçar todo mundo a logar de novo é uma
   consequência aceitável de um incidente de segurança real, não um custo
   operacional do dia a dia.

## Quando reconsiderar

- Quando o projeto tiver um ambiente de produção real com usuários ativos
  (não apenas dev/teste) — a essa altura, forçar logout de todos a cada
  rotação de segredo se torna um custo operacional real, não hipotético.
- Quando existir uma política formal de rotação de segredos (por exemplo,
  exigida por um requisito de compliance ou pela infraestrutura de nuvem
  escolhida).
- Quando múltiplas instâncias/réplicas do backend existirem e precisarem
  compartilhar uma transição de chave coordenada.

Quando qualquer um destes acontecer, o mecanismo de `kid` + múltiplas
chaves válidas é a extensão natural — aditiva sobre o que já existe
(`app.domains.auth.security`), não uma reescrita.

## Consequências

- Nenhuma mudança de código nesta fase. `JWT_SECRET_KEY` continua sendo um
  único valor, validado (tamanho mínimo, não-default) só em
  `_validate_production_config` (Fase 8.3/8.9).
- O risco ("rotacionar o segredo derruba todas as sessões de uma vez")
  permanece documentado no runbook de incidentes (relatório final da Fase
  8, "Secret compromised") como um comportamento esperado, não uma falha.
