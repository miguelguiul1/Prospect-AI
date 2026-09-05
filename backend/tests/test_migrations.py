"""Confirma explicitamente que a migration inicial da Fase 0 criou o schema
esperado — além da validação implícita de que toda a suíte depende da
fixture `_migrated_schema` (conftest.py) rodar `alembic upgrade head` com
sucesso antes de qualquer teste.
"""
from __future__ import annotations

from sqlalchemy import inspect

from app.db.session import engine

EXPECTED_TABLES = {
    "companies",
    "regions",
    "categories",
    "company_sources",
    "identity_merge_logs",
    "evidence",
    "audit_snapshots",
    "website_quality_snapshots",
    "opportunity_scores",
    "search_runs",
    "provider_usage_records",
    # Tabela interna do próprio Alembic para rastrear a versão aplicada.
    "alembic_version",
}


def test_migration_creates_all_expected_tables() -> None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())

    assert EXPECTED_TABLES.issubset(tables)


def test_company_sources_has_unique_constraint_on_source_and_external_id() -> None:
    inspector = inspect(engine)
    unique_constraints = inspector.get_unique_constraints("company_sources")

    assert any(
        set(constraint["column_names"]) == {"source", "external_id"}
        for constraint in unique_constraints
    )
