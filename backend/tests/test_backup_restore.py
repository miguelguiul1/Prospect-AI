"""Prova real de um ciclo de backup + restore (Fase 8.8).

**Importante sobre o que isto prova e o que não prova**: o mecanismo de
backup físico usado aqui — copiar os bytes do arquivo `.db` — é como
backup/restore funciona de verdade em SQLite (não há um `pg_dump`
equivalente necessário: o arquivo inteiro é o banco). Isto NÃO generaliza
para PostgreSQL, onde o mecanismo real de produção seria `pg_dump`/
`pg_restore` ou WAL archiving + PITR — nenhum dos dois foi executado nesta
sessão, porque não há PostgreSQL real disponível (ver
docs/production-readiness.md, seção Backup/Recovery, F8.8). O valor deste
teste é provar, pela primeira vez no projeto, que O CONCEITO de "backup é
uma cópia íntegra, restore é usar essa cópia depois de uma perda" funciona
de ponta a ponta contra o SGBD que esta sessão realmente tem disponível —
não é uma simulação do procedimento real de produção.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _migrate_to_head(db_path: Path) -> None:
    """Roda `alembic upgrade head` como subprocesso próprio, com
    `DATABASE_URL` isolado — `migrations/env.py` lê a URL de
    `app.core.config.get_settings()` (cacheado no processo do pytest),
    então rodar no mesmo processo aplicaria a migration no banco
    COMPARTILHADO da sessão de testes por engano, não neste arquivo
    temporário (mesmo cuidado de `test_migrations_roundtrip.py`)."""
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{db_path}"
    env["REDIS_URL"] = "redis://localhost:6399/0"
    env["APP_ENV"] = "development"
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(BACKEND_DIR),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, f"alembic upgrade head falhou:\n{result.stdout}\n{result.stderr}"


def test_backup_copy_survives_deletion_of_the_original_database() -> None:
    """Cria dados reais, "faz backup" (cópia física do arquivo), simula uma
    perda total do banco original (delete), e prova que o restore (copiar o
    backup de volta) recupera os dados exatamente como estavam."""
    from app.domains.companies.models import Company

    primary_path = Path(tempfile.gettempdir()) / f"prospect_ai_backup_primary_{uuid.uuid4().hex}.db"
    backup_path = Path(tempfile.gettempdir()) / f"prospect_ai_backup_copy_{uuid.uuid4().hex}.db"
    restored_path = Path(tempfile.gettempdir()) / f"prospect_ai_backup_restored_{uuid.uuid4().hex}.db"

    try:
        _migrate_to_head(primary_path)

        primary_engine = create_engine(f"sqlite:///{primary_path}", future=True)
        company_id = uuid.uuid4()
        with Session(primary_engine) as session:
            session.add(Company(id=company_id, canonical_name="Empresa Crítica de Produção LTDA"))
            session.commit()
        primary_engine.dispose()

        # "Backup": cópia física do arquivo, íntegra, feita com o banco em
        # repouso (sem escrita concorrente durante a cópia neste teste).
        shutil.copy2(primary_path, backup_path)

        # "Desastre": o banco original é perdido por completo.
        primary_path.unlink()
        assert not primary_path.exists()

        # "Restore": o backup se torna o banco em produção.
        shutil.copy2(backup_path, restored_path)
        restored_engine = create_engine(f"sqlite:///{restored_path}", future=True)
        with Session(restored_engine) as session:
            recovered = session.execute(
                select(Company).where(Company.id == company_id)
            ).scalar_one()
            assert recovered.canonical_name == "Empresa Crítica de Produção LTDA"
        restored_engine.dispose()
    finally:
        for path in (primary_path, backup_path, restored_path):
            if path.exists():
                path.unlink()
