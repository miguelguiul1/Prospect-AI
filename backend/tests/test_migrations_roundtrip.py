"""Prova real de que a cadeia de `downgrade()` funciona de ponta a ponta
(Fase 8.8).

Toda a suíte já prova `alembic upgrade head` a cada execução (fixture
`_migrated_schema` em `conftest.py`), mas nunca havia, em toda a história
do projeto (F0-F7), uma execução real de `downgrade()` — nem parcial, nem
total. Isso importa para backup/recovery: um plano de rollback de migration
que nunca foi executado de verdade é uma suposição, não um fato.

**Por que via subprocesso, não `alembic.command` direto no processo do
pytest**: `migrations/env.py` obtém a URL do banco de
`app.core.config.get_settings()` (cacheado com `@lru_cache`), ignorando
qualquer `sqlalchemy.url` setado manualmente em um objeto `Config` no
mesmo processo — é assim que `env.py` garante uma única fonte de verdade
para o resto da aplicação. Rodar `alembic` como um processo `python -m`
separado, com `DATABASE_URL` apontando só para um arquivo SQLite temporário
próprio deste teste, evita both corromper o banco compartilhado da sessão
de testes E editar `env.py` só para acomodar este teste.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

from sqlalchemy import create_engine, inspect

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _run_alembic(*args: str, db_path: Path) -> None:
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{db_path}"
    env["REDIS_URL"] = "redis://localhost:6399/0"
    env["APP_ENV"] = "development"
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=str(BACKEND_DIR),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, f"alembic {' '.join(args)} falhou:\n{result.stdout}\n{result.stderr}"


def test_full_downgrade_to_base_then_upgrade_head_round_trips_cleanly() -> None:
    """Prova real, não dedução por leitura de código: sobe até `head`,
    desce até `base` (executa TODOS os 10 `downgrade()` em cadeia pela
    primeira vez neste projeto), confirma que só `alembic_version` resta,
    e sobe de novo até `head`, confirmando que o schema final é idêntico
    ao original."""
    db_path = Path(tempfile.gettempdir()) / f"prospect_ai_migration_roundtrip_{uuid.uuid4().hex}.db"
    engine = create_engine(f"sqlite:///{db_path}", future=True)

    try:
        _run_alembic("upgrade", "head", db_path=db_path)
        tables_after_first_upgrade = set(inspect(engine).get_table_names())
        assert "opportunities" in tables_after_first_upgrade
        assert "users" in tables_after_first_upgrade
        assert "outreach_messages" in tables_after_first_upgrade

        _run_alembic("downgrade", "base", db_path=db_path)
        engine.dispose()
        tables_after_downgrade = set(inspect(engine).get_table_names())
        assert tables_after_downgrade == {"alembic_version"}, (
            f"downgrade('base') deveria remover TODAS as tabelas de domínio, sobrou: "
            f"{tables_after_downgrade - {'alembic_version'}}"
        )

        _run_alembic("upgrade", "head", db_path=db_path)
        engine.dispose()
        tables_after_second_upgrade = set(inspect(engine).get_table_names())
        assert tables_after_second_upgrade == tables_after_first_upgrade, (
            "o schema recriado após um round-trip completo deveria ser idêntico ao original"
        )
    finally:
        engine.dispose()
        if db_path.exists():
            db_path.unlink()


def test_downgrading_one_step_from_head_removes_only_the_last_migration_tables() -> None:
    """Rollback parcial (o caso real de operação: reverter só a última
    migration aplicada, não o banco inteiro) — prova que `0010_crm_outreach`
    reverte de forma isolada, sem afetar as tabelas de `0009` e anteriores."""
    db_path = Path(tempfile.gettempdir()) / f"prospect_ai_migration_partial_{uuid.uuid4().hex}.db"
    engine = create_engine(f"sqlite:///{db_path}", future=True)

    try:
        _run_alembic("upgrade", "head", db_path=db_path)
        _run_alembic("downgrade", "-1", db_path=db_path)
        engine.dispose()

        tables = set(inspect(engine).get_table_names())
        assert "outreach_messages" not in tables
        # Tabelas de migrations anteriores continuam intactas.
        assert "opportunities" in tables
        assert "activities" in tables
        assert "contacts" in tables
    finally:
        engine.dispose()
        if db_path.exists():
            db_path.unlink()
