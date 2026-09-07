"""Validação contra PostgreSQL REAL (Fase 8) — nunca simulado.

Diferente do resto da suíte (que roda inteiramente contra SQLite, por
desenho, desde a Fase 0 — ver `tests/conftest.py`), estes testes exigem um
PostgreSQL de verdade e usam sua PRÓPRIA URL de conexão
(`REAL_POSTGRES_URL`), independente do `DATABASE_URL` que o resto da suíte
já fixou como SQLite antes de qualquer import.

Se não houver PostgreSQL real acessível (o caso de toda máquina de
desenvolvimento usada neste projeto até a Fase 8), a suíte inteira deste
arquivo é pulada com um motivo explícito — nunca falha silenciosamente,
nunca finge sucesso. Em CI (`.github/workflows/ci.yml`), um serviço
`postgres:16-alpine` real é provisionado e estes testes executam de
verdade — a primeira validação genuína de PostgreSQL na história do
projeto.
"""
from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError, OperationalError

_CONSTRAINT_VIOLATION_ERRORS = (IntegrityError, OperationalError)

REAL_POSTGRES_URL = os.environ.get(
    "REAL_POSTGRES_URL", "postgresql+psycopg://prospect:prospect@localhost:5432/prospect_ai_ci"
)


def _postgres_available() -> bool:
    """`connect_timeout` curto e explícito (parâmetro libpq real, via
    `connect_args`) — sem isso, uma tentativa de conexão a um host/porta que
    não responde (em vez de recusar a conexão imediatamente) pode travar por
    dezenas de segundos, o mesmo problema já observado com o Redis padrão do
    projeto (`app.jobs.queue.get_redis_connection`) e corrigido do mesmo
    jeito: falhar rápido é obrigatório para uma checagem de disponibilidade."""
    try:
        engine = create_engine(
            REAL_POSTGRES_URL, pool_pre_ping=True, connect_args={"connect_timeout": 2}
        )
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
        return True
    except Exception:  # noqa: BLE001 - qualquer falha de conectividade significa "indisponível"
        return False


pytestmark = pytest.mark.skipif(
    not _postgres_available(),
    reason=(
        "PostgreSQL real indisponível (REAL_POSTGRES_URL não conectou). "
        "Isto é esperado em ambiente de desenvolvimento local sem Docker — "
        "ver docs/production-readiness.md, seção 'Infraestrutura real'."
    ),
)


@pytest.fixture()
def pg_engine():
    engine = create_engine(
        REAL_POSTGRES_URL, pool_pre_ping=True, future=True, connect_args={"connect_timeout": 5}
    )
    yield engine
    engine.dispose()


class TestConnectivity:
    def test_connects_and_runs_a_trivial_query(self, pg_engine) -> None:
        with pg_engine.connect() as conn:
            result = conn.execute(text("SELECT 1")).scalar()
        assert result == 1

    def test_server_version_is_at_least_postgres_14(self, pg_engine) -> None:
        with pg_engine.connect() as conn:
            version = conn.execute(text("SHOW server_version_num")).scalar()
        assert int(version) >= 140000, f"PostgreSQL muito antigo: {version}"


class TestMigrationsAgainstRealPostgres:
    """Requer que `alembic upgrade head` já tenha sido executado contra
    REAL_POSTGRES_URL antes da suíte rodar (ver o job de CI) — aqui só
    validamos o RESULTADO real do schema, não re-executamos a migration."""

    def test_all_f0_to_f7_tables_exist(self, pg_engine) -> None:
        expected_tables = {
            "companies", "regions", "categories", "company_sources", "evidence",
            "audit_snapshots", "website_quality_snapshots", "search_runs",
            "provider_usage_records", "dedup_candidates", "identity_merge_logs",
            "opportunity_scores", "sales_briefs", "prototypes",
            "users", "pipeline_stages", "opportunities", "contacts",
            "activities", "outreach_messages", "alembic_version",
        }
        with pg_engine.connect() as conn:
            rows = conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            ).all()
        actual_tables = {row[0] for row in rows}
        missing = expected_tables - actual_tables
        assert not missing, f"Tabelas ausentes no PostgreSQL real: {missing}"

    def test_opportunities_partial_unique_index_exists_and_is_partial(self, pg_engine) -> None:
        """Prova, contra o PostgreSQL real (não SQLite), que o índice único
        parcial que garante 'no máximo uma Opportunity OPEN por empresa'
        (Fase 7) realmente existe e realmente é parcial (tem uma cláusula
        WHERE) — não apenas um índice único comum."""
        with pg_engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT indexdef FROM pg_indexes "
                    "WHERE indexname = 'uq_opportunities_company_open'"
                )
            ).first()
        assert row is not None, "Índice uq_opportunities_company_open não encontrado"
        indexdef = row[0]
        assert "UNIQUE" in indexdef
        assert "WHERE" in indexdef
        assert "OPEN" in indexdef

    def test_opportunity_stage_change_race_condition_is_visible(self, pg_engine) -> None:
        """Documenta (não 'corrige') o achado da auditoria F8.0, seção 14:
        duas transações concorrentes mudando o stage da MESMA Opportunity
        não têm lock explícito — a última a committar vence, sem erro. Este
        teste prova isso empiricamente contra PostgreSQL real (READ
        COMMITTED, o isolamento padrão), não apenas por revisão de código."""
        import uuid as _uuid

        from sqlalchemy.orm import sessionmaker

        Session = sessionmaker(bind=pg_engine, future=True)
        table = "opportunities_race_test_" + _uuid.uuid4().hex[:8]

        with pg_engine.begin() as conn:
            conn.execute(text(f"CREATE TABLE {table} (id INT PRIMARY KEY, stage TEXT NOT NULL)"))
            conn.execute(text(f"INSERT INTO {table} (id, stage) VALUES (1, 'new')"))

        try:
            session_a = Session()
            session_b = Session()
            try:
                # Duas transações leem o mesmo estado "new" antes de qualquer uma escrever —
                # exatamente o cenário de corrida entre duas requisições HTTP concorrentes.
                session_a.execute(text(f"SELECT stage FROM {table} WHERE id = 1")).scalar()
                session_b.execute(text(f"SELECT stage FROM {table} WHERE id = 1")).scalar()

                session_a.execute(text(f"UPDATE {table} SET stage = 'qualified' WHERE id = 1"))
                session_a.commit()

                session_b.execute(text(f"UPDATE {table} SET stage = 'negotiation' WHERE id = 1"))
                session_b.commit()  # nunca levanta erro sob READ COMMITTED — confirma o achado do F8.0

                final = session_a.execute(text(f"SELECT stage FROM {table} WHERE id = 1")).scalar()
                assert final == "negotiation"  # a última a committar venceu, silenciosamente
            finally:
                session_a.close()
                session_b.close()
        finally:
            with pg_engine.begin() as conn:
                conn.execute(text(f"DROP TABLE IF EXISTS {table}"))


class TestOpportunityConcurrencyReal:
    """Valida ao vivo, contra PostgreSQL real, o cenário mais crítico do
    F8.0 seção 4/14: duas 'requisições' (aqui, duas transações/conexões
    separadas) tentando criar uma Opportunity OPEN para a MESMA empresa ao
    mesmo tempo."""

    def test_second_concurrent_open_opportunity_is_rejected_by_the_database(self, pg_engine) -> None:
        from sqlalchemy.orm import sessionmaker

        Session = sessionmaker(bind=pg_engine, future=True)
        company_id = uuid.uuid4()
        owner_id = uuid.uuid4()
        stage_id = uuid.uuid4()

        with pg_engine.begin() as conn:
            # Tabela isolada e mínima, só com a constraint que queremos provar —
            # evita depender do schema completo de `opportunities` (FKs para
            # companies/users/pipeline_stages) só para este teste de baixo nível.
            conn.execute(text("DROP TABLE IF EXISTS opp_concurrency_test"))
            conn.execute(
                text(
                    "CREATE TABLE opp_concurrency_test ("
                    "id UUID PRIMARY KEY, company_id UUID NOT NULL, status TEXT NOT NULL)"
                )
            )
            conn.execute(
                text(
                    "CREATE UNIQUE INDEX uq_opp_concurrency_test_open "
                    "ON opp_concurrency_test (company_id) WHERE status = 'OPEN'"
                )
            )

        try:
            session_a = Session()
            session_b = Session()
            try:
                session_a.execute(
                    text(
                        "INSERT INTO opp_concurrency_test (id, company_id, status) "
                        "VALUES (:id, :company_id, 'OPEN')"
                    ),
                    {"id": uuid.uuid4(), "company_id": company_id},
                )
                session_a.commit()

                with pytest.raises(_CONSTRAINT_VIOLATION_ERRORS):
                    session_b.execute(
                        text(
                            "INSERT INTO opp_concurrency_test (id, company_id, status) "
                            "VALUES (:id, :company_id, 'OPEN')"
                        ),
                        {"id": uuid.uuid4(), "company_id": company_id},
                    )
                    session_b.commit()
                session_b.rollback()

                count = session_a.execute(
                    text("SELECT COUNT(*) FROM opp_concurrency_test WHERE company_id = :c AND status = 'OPEN'"),
                    {"c": company_id},
                ).scalar()
                assert count == 1, "PostgreSQL permitiu duas Opportunity OPEN para a mesma empresa"
            finally:
                session_a.close()
                session_b.close()
        finally:
            with pg_engine.begin() as conn:
                conn.execute(text("DROP TABLE IF EXISTS opp_concurrency_test"))
