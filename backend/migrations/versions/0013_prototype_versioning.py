"""prototype versioning and refinement (Prompt 12)

Uma tabela nova (`prototype_versions`) mais três colunas novas em
`prototype_generation_runs` (`instruction`, `based_on_version_number`,
`diff_summary`) — todas nullable, nenhuma quebra retroativa. `op.add_column`
puro (não `batch_alter_table`): nenhuma das três colunas novas tem FK nem
constraint, só `ADD COLUMN` simples, que o SQLite já suporta nativamente
(diferente da FK adicionada em 0011, que exigiu o modo batch).

`prototype_versions.generation_run_id` é a única FK nova, e aponta para
uma tabela já existente (`prototype_generation_runs`) — sem dependência
circular: `prototype_generation_runs.based_on_version_number` é só um
inteiro solto, nunca uma FK para `prototype_versions` (ver docstring de
`GenerationRun.based_on_version_number` em
`app/domains/prototypes/models.py` para o motivo).

Revision ID: 0013prototypeversion
Revises: 0012prototypegen
Create Date: 2026-09-07 20:00:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0013prototypeversion'
down_revision: str | None = '0012prototypegen'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('prototype_generation_runs', sa.Column('instruction', sa.String(length=4000), nullable=True))
    op.add_column('prototype_generation_runs', sa.Column('based_on_version_number', sa.Integer(), nullable=True))
    op.add_column('prototype_generation_runs', sa.Column('diff_summary', sa.JSON(), nullable=True))

    op.create_table('prototype_versions',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('prototype_id', sa.Uuid(), nullable=False),
    sa.Column('version_number', sa.Integer(), nullable=False),
    sa.Column('components', sa.JSON(), nullable=False),
    sa.Column('generation_run_id', sa.Uuid(), nullable=True),
    sa.Column('restored_from_version_number', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['generation_run_id'], ['prototype_generation_runs.id'], name=op.f('fk_prototype_versions_generation_run_id_prototype_generation_runs')),
    sa.ForeignKeyConstraint(['prototype_id'], ['prototypes.id'], name=op.f('fk_prototype_versions_prototype_id_prototypes')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_prototype_versions')),
    sa.UniqueConstraint('prototype_id', 'version_number', name='uq_prototype_versions_prototype_id_version_number')
    )
    op.create_index(op.f('ix_prototype_versions_prototype_id'), 'prototype_versions', ['prototype_id'], unique=False)
    op.create_index(op.f('ix_prototype_versions_generation_run_id'), 'prototype_versions', ['generation_run_id'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_prototype_versions_generation_run_id'), table_name='prototype_versions')
    op.drop_index(op.f('ix_prototype_versions_prototype_id'), table_name='prototype_versions')
    op.drop_table('prototype_versions')

    op.drop_column('prototype_generation_runs', 'diff_summary')
    op.drop_column('prototype_generation_runs', 'based_on_version_number')
    op.drop_column('prototype_generation_runs', 'instruction')
