"""Testes de `GET /metrics` e do registro de métricas em processo (Fase 8.6)."""
from __future__ import annotations

import pytest

from app.core import metrics


@pytest.fixture(autouse=True)
def _reset_metrics():
    metrics.reset()
    yield
    metrics.reset()


class TestMetricsRegistry:
    def test_increment_and_render(self) -> None:
        metrics.increment("test_counter_total", {"label": "a"})
        metrics.increment("test_counter_total", {"label": "a"})
        metrics.increment("test_counter_total", {"label": "b"})

        text = metrics.render_prometheus_text()

        assert 'test_counter_total{label="a"} 2' in text
        assert 'test_counter_total{label="b"} 1' in text
        assert "# TYPE test_counter_total counter" in text

    def test_observe_records_sum_and_count(self) -> None:
        metrics.observe("test_latency", 10.0, {"path": "/x"})
        metrics.observe("test_latency", 20.0, {"path": "/x"})

        text = metrics.render_prometheus_text()

        assert 'test_latency_ms_sum{path="/x"} 30.000' in text
        assert 'test_latency_ms_count{path="/x"} 2' in text

    def test_no_labels_renders_bare_metric_name(self) -> None:
        metrics.increment("test_simple_total")
        text = metrics.render_prometheus_text()
        assert "test_simple_total 1" in text

    def test_reset_clears_everything(self) -> None:
        metrics.increment("test_counter_total")
        metrics.reset()
        assert metrics.render_prometheus_text() == ""


class TestMetricsEndpoint:
    def test_metrics_endpoint_is_public_and_returns_text(self, client) -> None:
        response = client.get("/metrics")
        assert response.status_code == 200
        assert "text/plain" in response.headers["content-type"]

    def test_http_requests_are_counted(self, client) -> None:
        client.get("/health")
        client.get("/health")

        response = client.get("/metrics")
        assert 'http_requests_total{method="GET",path="/health",status="2xx"}' in response.text

    def test_auth_failures_are_counted(self, client) -> None:
        client.get("/api/auth/me")  # sem token

        response = client.get("/metrics")
        assert 'auth_failures_total{reason="missing_token"}' in response.text
