#!/usr/bin/env python
"""Alerta simples de saúde do sistema (Prompt 10, seção 2.3).

Achado aberto da Fase 8 ("Remaining Risks"): `/health/dependencies` e
`/metrics` existem desde F8.6, mas nada olha para eles automaticamente —
hoje um PostgreSQL fora do ar só é percebido manualmente. Este script
fecha só a checagem, não o alerta em si: consulta `/health/dependencies`
de um backend real e sai com um código de saída != 0 e uma mensagem clara
em stderr quando algo está degradado ou fora do ar.

**Não integra com nenhum serviço de alerta externo** (PagerDuty, Slack,
e-mail, etc.) — decisão explícita desta fase, não uma limitação técnica.
Este script é a peça que um cron/orquestrador externo chamaria; o que
fazer com um código de saída != 0 (notificar alguém, abrir um incidente)
é responsabilidade de quem o agenda, não deste script.

Códigos de saída:
    0  saudável (`status == "ok"`, nenhuma dependência degradada)
    1  degradado (ex.: Redis fora do ar — sistema continua no ar)
    2  not_ready (PostgreSQL fora do ar) ou erro de conexão/HTTP

## Agendamento sugerido em produção (documentado, nunca configurado de
## verdade nesta sessão — não há orquestrador real disponível)

- **cron** (mais simples, para uma única instância):
  `*/5 * * * * /usr/bin/python /app/scripts/healthcheck_alert.py --base-url http://localhost:8000 || mail -s "Prospect AI degradado" ops@example.com`
- **Kubernetes CronJob** ou equivalente do provedor de hospedagem,
  redirecionando um código de saída != 0 para o sistema de alerta já usado
  pela equipe (PagerDuty, Opsgenie, um canal do Slack via webhook) — a
  integração fica inteiramente do lado de quem agenda, este script nunca
  precisa saber que serviço de alerta existe.
- Intervalo sugerido: 1-5 minutos — mais frequente que isso não agrega
  muito para uma aplicação deste porte; menos frequente atrasa a detecção
  além do razoável.

Uso: `python scripts/healthcheck_alert.py [--base-url URL] [--timeout SEGUNDOS]`
"""
from __future__ import annotations

import argparse
import sys

import httpx

EXIT_OK = 0
EXIT_DEGRADED = 1
EXIT_NOT_READY = 2


def evaluate_health(status_code: int, body: dict) -> tuple[int, str]:
    """Lógica pura de decisão, separada da chamada HTTP (Prompt 10, seção
    3 — testável sem mockar rede: recebe o status HTTP e o JSON já
    decodificados, devolve o código de saída e a mensagem para stderr/
    stdout). Espelha exatamente a semântica de `/health/dependencies`
    definida em F8.6: só PostgreSQL fora do ar é `not_ready`; Redis vira
    `"degraded: ..."` sem derrubar o status geral.
    """
    status = body.get("status")
    checks = body.get("checks", {})

    # O corpo JSON é a fonte de verdade quando presente e reconhecível —
    # checado ANTES do código HTTP, porque `/health/dependencies` já
    # retorna 503 justamente quando `status == "not_ready"` (F8.6): tratar
    # "HTTP inesperado" e "not_ready" como o mesmo caso perderia a
    # distinção de mensagem entre "o endpoint respondeu dizendo que está
    # fora do ar" e "o endpoint nem respondeu direito".
    if status == "not_ready":
        return EXIT_NOT_READY, f"sistema NOT_READY (HTTP {status_code}) — checks: {checks}"

    if status_code != 200:
        return EXIT_NOT_READY, f"/health/dependencies retornou HTTP {status_code} inesperado: {body}"

    degraded = [
        name for name, value in checks.items() if isinstance(value, str) and value.startswith("degraded")
    ]
    if degraded:
        return EXIT_DEGRADED, f"dependências degradadas: {degraded} — checks: {checks}"

    return EXIT_OK, "saudável — todas as dependências OK"


def check_health(base_url: str, timeout: float = 5.0) -> tuple[int, str]:
    try:
        response = httpx.get(f"{base_url}/health/dependencies", timeout=timeout)
    except httpx.TransportError as exc:
        return EXIT_NOT_READY, f"não foi possível conectar a {base_url}/health/dependencies: {exc}"

    try:
        body = response.json()
    except ValueError:
        body = {"raw": response.text[:500]}

    return evaluate_health(response.status_code, body)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Checa /health/dependencies e sai com código != 0 se degradado.")
    parser.add_argument("--base-url", default="http://localhost:8000", help="URL base do backend Prospect AI")
    parser.add_argument("--timeout", type=float, default=5.0, help="Timeout da requisição, em segundos")
    args = parser.parse_args(argv)

    exit_code, message = check_health(args.base_url, timeout=args.timeout)
    if exit_code == EXIT_OK:
        print(f"OK: {message}")
    else:
        print(f"ALERTA ({'degradado' if exit_code == EXIT_DEGRADED else 'not_ready/erro'}): {message}", file=sys.stderr)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
