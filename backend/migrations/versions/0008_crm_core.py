"""crm core (pipeline stages + opportunities)

Revision ID: f7c2crm0008
Revises: f7a1u5er0007
Create Date: 2026-09-07 00:05:00.000000

"""
import uuid
from collections.abc import Sequence
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f7c2crm0008'
down_revision: str | None = 'f7a1u5er0007'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Etapas padrão do funil (Prompt 11, seção 7.1) — `key` é o identificador
# estável usado por código; `name` é só o rótulo exibido, livremente
# editável depois sem quebrar nada.
_DEFAULT_STAGES = [
    ("new", "Novo", 1, False, False),
    ("qualified", "Qualificado", 2, False, False),
    ("contacted", "Contato realizado", 3, False, False),
    ("meeting", "Reunião", 4, False, False),
    ("proposal", "Proposta", 5, False, False),
    ("negotiation", "Negociação", 6, False, False),
    ("won", "Ganho", 7, True, False),
    ("lost", "Perdido", 8, False, True),
]


def upgrade() -> None:
    op.create_table('pipeline_stages',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('key', sa.String(length=40), nullable=False),
    sa.Column('name', sa.String(length=80), nullable=False),
    sa.Column('order', sa.Integer(), nullable=False),
    sa.Column('is_won', sa.Boolean(), nullable=False),
    sa.Column('is_lost', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_pipeline_stages')),
    sa.UniqueConstraint('key', name=op.f('uq_pipeline_stages_key')),
    sa.UniqueConstraint('order', name=op.f('uq_pipeline_stages_order')),
    )

    stages_table = sa.table(
        'pipeline_stages',
        sa.column('id', sa.Uuid()),
        sa.column('key', sa.String()),
        sa.column('name', sa.String()),
        sa.column('order', sa.Integer()),
        sa.column('is_won', sa.Boolean()),
        sa.column('is_lost', sa.Boolean()),
        sa.column('created_at', sa.DateTime(timezone=True)),
    )
    now = datetime.now(timezone.utc)
    op.bulk_insert(
        stages_table,
        [
            {
                "id": uuid.uuid4(),
                "key": key,
                "name": name,
                "order": order,
                "is_won": is_won,
                "is_lost": is_lost,
                "created_at": now,
            }
            for key, name, order, is_won, is_lost in _DEFAULT_STAGES
        ],
    )

    op.create_table('opportunities',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('company_id', sa.Uuid(), nullable=False),
    sa.Column('owner_id', sa.Uuid(), nullable=False),
    sa.Column('stage_id', sa.Uuid(), nullable=False),
    sa.Column('status', sa.Enum('OPEN', 'WON', 'LOST', 'ARCHIVED', name='opportunitystatus', native_enum=False, length=20), nullable=False),
    sa.Column('priority', sa.Enum('LOW', 'MEDIUM', 'HIGH', name='opportunitypriority', native_enum=False, length=20), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['company_id'], ['companies.id'], name=op.f('fk_opportunities_company_id_companies')),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], name=op.f('fk_opportunities_owner_id_users')),
    sa.ForeignKeyConstraint(['stage_id'], ['pipeline_stages.id'], name=op.f('fk_opportunities_stage_id_pipeline_stages')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_opportunities'))
    )
    op.create_index(op.f('ix_opportunities_company_id'), 'opportunities', ['company_id'], unique=False)
    op.create_index(op.f('ix_opportunities_owner_id'), 'opportunities', ['owner_id'], unique=False)
    op.create_index(op.f('ix_opportunities_stage_id'), 'opportunities', ['stage_id'], unique=False)
    # Índice único PARCIAL: no máximo uma Opportunity com status='open' por
    # empresa — é isso que torna a criação idempotente também no banco, não
    # só na aplicação (Prompt 11, seções 6 e 24).
    op.create_index(
        'uq_opportunities_company_open',
        'opportunities',
        ['company_id'],
        unique=True,
        sqlite_where=sa.text("status = 'OPEN'"),
        postgresql_where=sa.text("status = 'OPEN'"),
    )


def downgrade() -> None:
    op.drop_index('uq_opportunities_company_open', table_name='opportunities')
    op.drop_index(op.f('ix_opportunities_stage_id'), table_name='opportunities')
    op.drop_index(op.f('ix_opportunities_owner_id'), table_name='opportunities')
    op.drop_index(op.f('ix_opportunities_company_id'), table_name='opportunities')
    op.drop_table('opportunities')
    op.drop_table('pipeline_stages')
