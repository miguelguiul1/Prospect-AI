"""Teste de carga local real (Fase 8.7) contra um servidor de verdade.

Diferente da suíte `pytest` (que usa `TestClient`, sem socket TCP real e com
uma única conexão de banco compartilhada por teste — ver `tests/conftest.py`),
este script:

1. Sobe um `uvicorn` real, em um processo separado, escutando em uma porta
   TCP real.
2. Aponta esse processo para um arquivo SQLite dedicado e recém-migrado
   (`alembic upgrade head` de verdade) — não o Postgres de produção, que não
   está disponível nesta máquina (ver docs/production-readiness.md). Isso é
   deliberadamente rotulado como tal no relatório: o resultado prova a
   camada HTTP/aplicação sob concorrência real, mas os números de
   throughput/latência NÃO são os de Postgres (SQLite serializa escritas
   por processo; Postgres usa MVCC com locks por linha).
3. Faz requisições HTTP reais (via `httpx`), com `ThreadPoolExecutor` para
   concorrência real de threads do sistema operacional — não corrotinas
   simulando concorrência dentro do mesmo processo.

Uso: `python scripts/load_test.py` (a partir de `backend/`). Não faz parte
da suíte `pytest` — é uma ferramenta de diagnóstico executada manualmente,
como os scripts em `scripts/` já existentes no projeto.
"""
from __future__ import annotations

import os
import statistics
import subprocess
import sys
import tempfile
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
DB_PATH = Path(tempfile.gettempdir()) / f"prospect_ai_loadtest_{uuid.uuid4().hex}.db"
BASE_URL = "http://127.0.0.1:8899"


def _setup_environment() -> None:
    os.environ["DATABASE_URL"] = f"sqlite:///{DB_PATH}"
    os.environ["REDIS_URL"] = "redis://localhost:6399/0"
    os.environ["APP_ENV"] = "development"
    os.environ["JWT_SECRET_KEY"] = "load-test-secret-not-for-production"


def _migrate() -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    command.upgrade(cfg, "head")


def _seed_company() -> uuid.UUID:
    from app.db.session import SessionLocal
    from app.domains.companies.models import Company

    db = SessionLocal()
    try:
        company = Company(canonical_name="Empresa de Teste de Carga LTDA")
        db.add(company)
        db.commit()
        db.refresh(company)
        return company.id
    finally:
        db.close()


def _count_open_opportunities(company_id: uuid.UUID) -> int:
    from sqlalchemy import select

    from app.db.session import SessionLocal
    from app.domains.crm.enums import OpportunityStatus
    from app.domains.crm.models import Opportunity

    db = SessionLocal()
    try:
        stmt = select(Opportunity).where(
            Opportunity.company_id == company_id, Opportunity.status == OpportunityStatus.OPEN
        )
        return len(list(db.execute(stmt).scalars()))
    finally:
        db.close()


@dataclass
class ScenarioResult:
    name: str
    latencies_ms: list[float] = field(default_factory=list)
    statuses: list[int] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    wall_seconds: float = 0.0

    def summary(self) -> str:
        n = len(self.latencies_ms)
        if n == 0:
            return f"{self.name}: nenhuma requisição completada ({len(self.errors)} erros de transporte)"
        sorted_lat = sorted(self.latencies_ms)
        p50 = sorted_lat[int(0.50 * (n - 1))]
        p95 = sorted_lat[int(0.95 * (n - 1))]
        p99 = sorted_lat[int(0.99 * (n - 1))]
        error_count = sum(1 for s in self.statuses if s >= 500) + len(self.errors)
        rps = n / self.wall_seconds if self.wall_seconds > 0 else float("inf")
        status_counts: dict[int, int] = {}
        for s in self.statuses:
            status_counts[s] = status_counts.get(s, 0) + 1
        return (
            f"{self.name}:\n"
            f"  requisições: {n} em {self.wall_seconds:.2f}s ({rps:.1f} req/s)\n"
            f"  latência (ms): avg={statistics.mean(self.latencies_ms):.1f} "
            f"p50={p50:.1f} p95={p95:.1f} p99={p99:.1f} max={max(self.latencies_ms):.1f}\n"
            f"  status: {status_counts}\n"
            f"  erros de transporte (conexão recusada/timeout): {len(self.errors)}\n"
            f"  erros 5xx: {error_count - len(self.errors)}"
        )


def _run_concurrent(name: str, n_requests: int, concurrency: int, call) -> ScenarioResult:
    result = ScenarioResult(name=name)
    start = time.perf_counter()

    def _one(_: int) -> None:
        t0 = time.perf_counter()
        try:
            status_code = call()
            result.latencies_ms.append((time.perf_counter() - t0) * 1000)
            result.statuses.append(status_code)
        except Exception as exc:  # noqa: BLE001 - erro de transporte é um resultado válido a registrar
            result.errors.append(f"{exc.__class__.__name__}: {exc}")

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        list(pool.map(_one, range(n_requests)))

    result.wall_seconds = time.perf_counter() - start
    return result


def main() -> None:
    _setup_environment()
    sys.path.insert(0, str(BACKEND_DIR))

    _migrate()
    company_id = _seed_company()

    print(f"[load_test] banco: {DB_PATH}")
    print("[load_test] subindo uvicorn real em processo separado...")
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8899"],
        cwd=str(BACKEND_DIR),
        env=os.environ.copy(),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    import httpx

    try:
        for _ in range(50):
            try:
                r = httpx.get(f"{BASE_URL}/health", timeout=1.0)
                if r.status_code == 200:
                    break
            except httpx.TransportError:
                pass
            time.sleep(0.2)
        else:
            raise RuntimeError("uvicorn não respondeu a /health a tempo")

        print("[load_test] servidor no ar. Registrando usuário de teste...")
        email = f"loadtest+{uuid.uuid4().hex[:8]}@example.com"
        register_resp = httpx.post(
            f"{BASE_URL}/api/auth/register",
            json={"email": email, "name": "Load Test", "password": "senha-forte-123"},
            timeout=5.0,
        )
        register_resp.raise_for_status()
        token = register_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        results: list[ScenarioResult] = []

        # Cenário 1: liveness sob carga (sem banco) — baseline de throughput puro da stack HTTP.
        with httpx.Client(timeout=5.0) as client:
            results.append(
                _run_concurrent(
                    "1. GET /health (liveness, sem banco)",
                    n_requests=300,
                    concurrency=30,
                    call=lambda: client.get(f"{BASE_URL}/health").status_code,
                )
            )

        # Cenário 2: leitura autenticada com banco (lista de oportunidades).
        with httpx.Client(timeout=5.0, headers=headers) as client:
            results.append(
                _run_concurrent(
                    "2. GET /api/crm/opportunities (leitura autenticada, com banco)",
                    n_requests=150,
                    concurrency=15,
                    call=lambda: client.get(f"{BASE_URL}/api/crm/opportunities").status_code,
                )
            )

        # Cenário 3: corretude sob concorrência real — N requisições simultâneas
        # tentando criar a MESMA Opportunity (mesma empresa). O índice único
        # parcial (uq_opportunities_company_open) deve garantir, mesmo com
        # 15 threads reais e um servidor HTTP real, que só existe 1 linha
        # OPEN ao final — não uma dedução por leitura de código, uma prova
        # empírica (mesmo espírito de tests/infra/test_real_postgres.py,
        # mas aqui contra SQLite real, via HTTP real).
        with httpx.Client(timeout=5.0, headers=headers) as client:
            concurrency_result = _run_concurrent(
                "3. POST /api/crm/opportunities concorrente (mesma empresa)",
                n_requests=15,
                concurrency=15,
                call=lambda: client.post(
                    f"{BASE_URL}/api/crm/opportunities", json={"company_id": str(company_id)}
                ).status_code,
            )
        results.append(concurrency_result)
        open_count = _count_open_opportunities(company_id)
        print(f"[load_test] Opportunities OPEN para a empresa de teste após concorrência: {open_count}")
        assert open_count == 1, f"ESPERADO 1 Opportunity OPEN, encontrado {open_count} — índice único falhou!"

        # Cenário 4: rate limiting de login sob concorrência real (não sequencial
        # como os testes pytest existentes) — prova que o contador local_fallback
        # (protegido por threading.Lock) é de fato thread-safe sob carga real,
        # não só correto em teste de unidade sequencial.
        with httpx.Client(timeout=5.0) as client:
            login_result = _run_concurrent(
                "4. POST /api/auth/login concorrente, credenciais erradas (rate limit)",
                n_requests=20,
                concurrency=20,
                call=lambda: client.post(
                    f"{BASE_URL}/api/auth/login", json={"email": email, "password": "senha-errada"}
                ).status_code,
            )
        results.append(login_result)
        rate_limited_count = sum(1 for s in login_result.statuses if s == 429)
        unauthorized_count = sum(1 for s in login_result.statuses if s == 401)
        print(
            f"[load_test] login concorrente: {unauthorized_count} x 401 (credencial inválida), "
            f"{rate_limited_count} x 429 (rate limited)"
        )
        assert rate_limited_count > 0, "ESPERADO pelo menos 1 resposta 429 — rate limiter não bloqueou sob carga"

        print("\n" + "=" * 70)
        print("RESULTADOS — Fase 8.7 Load Test (local, SQLite, servidor uvicorn real)")
        print("=" * 70)
        for r in results:
            print(r.summary())
            print()

    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
        try:
            from app.db.session import engine

            engine.dispose()
        except Exception:  # noqa: BLE001 - limpeza best-effort, nunca deve mascarar o resultado do teste
            pass
        if DB_PATH.exists():
            try:
                DB_PATH.unlink()
            except PermissionError:
                print(f"[load_test] aviso: não foi possível remover {DB_PATH} (arquivo temporário, sem impacto)")


if __name__ == "__main__":
    main()
