"""Testes de `scripts/healthcheck_alert.py` (Prompt 10, seção 2.3).

`evaluate_health` é lógica pura (recebe status HTTP + JSON já decodificado,
devolve código de saída + mensagem) — testável sem nenhum mock de rede,
por desenho (ver docstring do módulo)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from healthcheck_alert import EXIT_DEGRADED, EXIT_NOT_READY, EXIT_OK, evaluate_health  # noqa: E402


class TestEvaluateHealth:
    def test_healthy_system_returns_exit_ok(self) -> None:
        code, message = evaluate_health(200, {"status": "ok", "checks": {"database": "ok", "redis": "ok"}})
        assert code == EXIT_OK
        assert "saudável" in message

    def test_not_ready_status_returns_exit_not_ready(self) -> None:
        code, message = evaluate_health(
            503, {"status": "not_ready", "checks": {"database": "error: conexão perdida", "redis": "ok"}}
        )
        assert code == EXIT_NOT_READY
        assert "NOT_READY" in message

    def test_degraded_redis_returns_exit_degraded_not_not_ready(self) -> None:
        """Espelha a semântica de F8.6: Redis degradado nunca é tratado com
        a mesma severidade de Postgres fora do ar."""
        code, message = evaluate_health(
            200, {"status": "ok", "checks": {"database": "ok", "redis": "degraded: ConnectionError"}}
        )
        assert code == EXIT_DEGRADED
        assert "redis" in message

    def test_unexpected_http_status_returns_exit_not_ready(self) -> None:
        code, message = evaluate_health(500, {"error": "internal_error"})
        assert code == EXIT_NOT_READY
        assert "500" in message

    def test_ok_status_with_no_degraded_checks_ignores_non_string_check_values(self) -> None:
        """Um valor não-string em `checks` (ex.: um booleano) nunca deve
        quebrar a checagem de prefixo `degraded`."""
        code, _ = evaluate_health(200, {"status": "ok", "checks": {"anthropic": "configured", "worker": True}})
        assert code == EXIT_OK


class TestCheckHealthAgainstARealRunningServer:
    """Prova de ponta a ponta contra um servidor real (não `TestClient`) —
    mesma metodologia de `scripts/load_test.py` (F8.7): sobe um `uvicorn`
    real em processo separado, chama o script contra ele de verdade."""

    def test_script_reports_ok_against_a_real_healthy_server(self) -> None:
        import os
        import subprocess
        import tempfile
        import time
        import uuid

        from healthcheck_alert import check_health

        backend_dir = Path(__file__).resolve().parents[1]
        db_path = Path(tempfile.gettempdir()) / f"prospect_ai_healthcheck_script_{uuid.uuid4().hex}.db"
        env = os.environ.copy()
        env["DATABASE_URL"] = f"sqlite:///{db_path}"
        env["REDIS_URL"] = "redis://localhost:6399/0"
        env["APP_ENV"] = "development"
        env["JWT_SECRET_KEY"] = "healthcheck-script-test-secret-not-for-prod"

        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=str(backend_dir), env=env, capture_output=True, text=True, timeout=60,
        )

        server = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8898"],
            cwd=str(backend_dir), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        try:
            import httpx

            for _ in range(50):
                try:
                    if httpx.get("http://127.0.0.1:8898/health", timeout=1.0).status_code == 200:
                        break
                except httpx.TransportError:
                    pass
                time.sleep(0.2)
            else:
                raise RuntimeError("uvicorn não respondeu a tempo")

            code, message = check_health("http://127.0.0.1:8898")

            # Redis está sempre indisponível nesta suíte (porta morta) — o
            # sistema real fica DEGRADED, não OK, e o script deve refletir
            # isso corretamente contra um servidor de verdade.
            assert code == EXIT_DEGRADED
            assert "redis" in message
        finally:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
            if db_path.exists():
                try:
                    db_path.unlink()
                except PermissionError:
                    pass  # arquivo temporário, sem impacto (mesmo padrão de scripts/load_test.py)
