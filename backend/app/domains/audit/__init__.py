"""Digital Audit + Website Quality Score (Fase 3).

Responde: "esta empresa tem um website próprio acessível, e quão boa é a
presença digital que ele representa?" Nunca decide oportunidade comercial
nem prioridade de venda — isso é Opportunity Score (Fase 4).

Submódulos:

- `ssrf.py` — validação de URL/IP contra acesso a redes internas.
- `http_client.py` — busca segura (timeout, limite de redirects, limite de
  tamanho de resposta), revalidando SSRF a cada redirecionamento.
- `html_signals.py` — extração determinística de sinais técnicos da página
  principal (sem crawling).
- `website_candidate.py` — escolha do candidato de website a partir do
  `Evidence` já existente da empresa.
- `scoring.py` — cálculo determinístico e reproduzível do Website Quality
  Score a partir dos sinais coletados.
- `service.py` — `DigitalAuditService`, que orquestra o fluxo completo.
- `jobs.py` — integração com a abstração de fila da Fase 0.

Ver docs/digital-audit.md para o desenho completo.
"""
