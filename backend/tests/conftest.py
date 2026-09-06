"""Fixtures compartilhadas dos testes da Fase 0.

Importante: as variáveis de ambiente de teste são definidas ANTES de
qualquer `import app...`, porque `app.db.session` cria a engine do
SQLAlchemy no momento da importação (a partir de `Settings.database_url`).

O schema de teste é construído executando as migrations reais do Alembic
(`alembic upgrade head`) contra um arquivo SQLite temporário — não com
`Base.metadata.create_all`. Isso valida de fato que a migration da Fase 0
funciona (critério de conclusão da Fase 0), e não apenas que os modelos em
memória são coerentes entre si.

Nesta máquina de desenvolvimento não há PostgreSQL nem Redis disponíveis
(nem Docker) — ver README.md, seção "Limitações conhecidas desta Fase 0".
Os testes rodam contra SQLite como stand-in para o Postgres real, e o
Redis não é exercitado por um servidor de verdade: `test_health.py` cobre
justamente o caso de dependência indisponível.
"""
from __future__ import annotations

import os
import tempfile
import uuid
from collections.abc import Generator
from pathlib import Path

import pytest

_TEST_DB_PATH = Path(tempfile.gettempdir()) / f"prospect_ai_test_{uuid.uuid4().hex}.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB_PATH}"
os.environ["REDIS_URL"] = "redis://localhost:6399/0"  # porta sem serviço: ver test_health.py
os.environ["APP_ENV"] = "test"

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import event  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.db.session import SessionLocal, engine, get_db  # noqa: E402
from app.main import app  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _alembic_config() -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    return cfg


@pytest.fixture(scope="session", autouse=True)
def _migrated_schema() -> Generator[None, None, None]:
    command.upgrade(_alembic_config(), "head")
    yield
    engine.dispose()
    if _TEST_DB_PATH.exists():
        _TEST_DB_PATH.unlink()


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    """Sessão isolada por teste: tudo é revertido ao final, mesmo que o
    próprio código de aplicação chame `session.commit()` (como a rota de
    Discovery faz, para que um worker separado veja o SearchRun).

    Usa o padrão recomendado pelo SQLAlchemy para "encaixar" uma Session em
    uma transação externa: a transação real (`transaction`) só é revertida
    no fim do teste; todo `commit()` do código de aplicação encerra apenas
    um SAVEPOINT aninhado, que este fixture reabre imediatamente via o
    evento `after_transaction_end`. Sem isso, um `commit()` do código sob
    teste commitaria de verdade no arquivo SQLite e vazaria estado entre
    testes.
    """
    connection = engine.connect()
    transaction = connection.begin()
    session = SessionLocal(bind=connection)

    nested = connection.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def _restart_savepoint(sess: Session, trans: object) -> None:
        nonlocal nested
        if not nested.is_active:
            nested = connection.begin_nested()

    try:
        yield session
    finally:
        session.close()
        # Um flush malsucedido (ex.: violação de UniqueConstraint) já
        # desassocia a transação da conexão por conta própria; só revertemos
        # explicitamente se ela ainda estiver ativa.
        if transaction.is_active:
            transaction.rollback()
        connection.close()


@pytest.fixture()
def client(db_session: Session) -> Generator[TestClient, None, None]:
    def _override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
