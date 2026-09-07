"""Métricas em processo, expostas em `GET /metrics` (Fase 8.6).

Deliberadamente simples: um registro em memória (thread-safe), sem
dependência nova, sem agregação entre processos/réplicas. Isto NÃO é uma
plataforma de observabilidade completa — é o mínimo proporcional ao
estágio atual do projeto (achado da auditoria F8.0, seção 11: "não existe
nenhuma métrica agregada, só log por requisição").

Formato de saída: texto de exposição do Prometheus (`text/plain; version
0.0.4`) — um formato amplamente reconhecido por qualquer coletor real
(Prometheus, Grafana Agent, Datadog via OpenMetrics, etc.), sem precisar
adotar nenhum deles agora. Se este processo reiniciar, as métricas
reiniciam com ele — comportamento aceito neste estágio (o mesmo já vale
para o fallback local de rate limiting, Fase 8.3).
"""
from __future__ import annotations

import threading
from collections import defaultdict

_lock = threading.Lock()
_counters: dict[tuple[str, tuple[tuple[str, str], ...]], int] = defaultdict(int)
_histogram_sums: dict[tuple[str, tuple[tuple[str, str], ...]], float] = defaultdict(float)
_histogram_counts: dict[tuple[str, tuple[tuple[str, str], ...]], int] = defaultdict(int)


def _key(name: str, labels: dict[str, str] | None) -> tuple[str, tuple[tuple[str, str], ...]]:
    return (name, tuple(sorted((labels or {}).items())))


def increment(name: str, labels: dict[str, str] | None = None, value: int = 1) -> None:
    with _lock:
        _counters[_key(name, labels)] += value


def observe(name: str, value_ms: float, labels: dict[str, str] | None = None) -> None:
    key = _key(name, labels)
    with _lock:
        _histogram_sums[key] += value_ms
        _histogram_counts[key] += 1


def reset() -> None:
    """Só para testes — nunca chamado pelo código de aplicação."""
    with _lock:
        _counters.clear()
        _histogram_sums.clear()
        _histogram_counts.clear()


def _format_labels(labels: tuple[tuple[str, str], ...]) -> str:
    if not labels:
        return ""
    parts = ",".join(f'{k}="{v}"' for k, v in labels)
    return f"{{{parts}}}"


def render_prometheus_text() -> str:
    lines: list[str] = []
    with _lock:
        counters = dict(_counters)
        sums = dict(_histogram_sums)
        counts = dict(_histogram_counts)

    seen_counter_names: set[str] = set()
    for (name, labels), value in sorted(counters.items()):
        if name not in seen_counter_names:
            lines.append(f"# TYPE {name} counter")
            seen_counter_names.add(name)
        lines.append(f"{name}{_format_labels(labels)} {value}")

    seen_hist_names: set[str] = set()
    for (name, labels) in sorted(sums.keys()):
        if name not in seen_hist_names:
            lines.append(f"# TYPE {name}_ms summary")
            seen_hist_names.add(name)
        key = (name, labels)
        lines.append(f"{name}_ms_sum{_format_labels(labels)} {sums[key]:.3f}")
        lines.append(f"{name}_ms_count{_format_labels(labels)} {counts[key]}")

    return "\n".join(lines) + "\n" if lines else ""


__all__ = ["increment", "observe", "render_prometheus_text", "reset"]
