"""prototype generation run and context snapshot (Prompt 11)

Duas tabelas novas, nenhuma alteração em tabela existente — a mais
simples das migrations desta série (`op.create_table` puro, sem
`batch_alter_table`, já que nada é adicionado a uma tabela já existente
desta vez).

Revision ID: 0012prototypegen
Revises: 0011prototypecompany
Create Date: 2026-09-07 18:00:20.265917

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0012prototypegen'
down_revision: str | None = '0011prototypecompany'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('prototype_generation_runs',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('prototype_id', sa.Uuid(), nullable=False),
    sa.Column('company_id', sa.Uuid(), nullable=False),
    sa.Column('status', sa.Enum('PENDING', 'SUCCEEDED', 'FAILED', name='generationstatus', native_enum=False, length=20), nullable=False),
    sa.Column('provider', sa.String(length=40), nullable=True),
    sa.Column('model', sa.String(length=80), nullable=True),
    sa.Column('prompt_version', sa.String(length=10), nullable=False),
    sa.Column('context_version', sa.String(length=10), nullable=False),
    sa.Column('input_tokens', sa.Integer(), nullable=True),
    sa.Column('output_tokens', sa.Integer(), nullable=True),
    sa.Column('duration_ms', sa.Float(), nullable=True),
    sa.Column('error_code', sa.String(length=60), nullable=True),
    sa.Column('error_message', sa.String(length=500), nullable=True),
    sa.Column('grounding_warnings', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['company_id'], ['companies.id'], name=op.f('fk_prototype_generation_runs_company_id_companies')),
    sa.ForeignKeyConstraint(['prototype_id'], ['prototypes.id'], name=op.f('fk_prototype_generation_runs_prototype_id_prototypes')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_prototype_generation_runs'))
    )
    op.create_index(op.f('ix_prototype_generation_runs_company_id'), 'prototype_generation_runs', ['company_id'], unique=False)
    op.create_index(op.f('ix_prototype_generation_runs_prototype_id'), 'prototype_generation_runs', ['prototype_id'], unique=False)
    op.create_table('prototype_context_snapshots',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('generation_run_id', sa.Uuid(), nullable=False),
    sa.Column('context', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['generation_run_id'], ['prototype_generation_runs.id'], name=op.f('fk_prototype_context_snapshots_generation_run_id_prototype_generation_runs')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_prototype_context_snapshots'))
    )
    op.create_index(op.f('ix_prototype_context_snapshots_generation_run_id'), 'prototype_context_snapshots', ['generation_run_id'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_prototype_context_snapshots_generation_run_id'), table_name='prototype_context_snapshots')
    op.drop_table('prototype_context_snapshots')
    op.drop_index(op.f('ix_prototype_generation_runs_prototype_id'), table_name='prototype_generation_runs')
    op.drop_index(op.f('ix_prototype_generation_runs_company_id'), table_name='prototype_generation_runs')
    op.drop_table('prototype_generation_runs')
