"""crm outreach (assisted outreach)

Revision ID: f7e4crm0010
Revises: f7d3crm0009
Create Date: 2026-09-07 00:15:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f7e4crm0010'
down_revision: str | None = 'f7d3crm0009'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('outreach_messages',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('opportunity_id', sa.Uuid(), nullable=False),
    sa.Column('contact_id', sa.Uuid(), nullable=True),
    sa.Column('channel', sa.Enum('EMAIL', 'WHATSAPP', 'OTHER', name='outreachchannel', native_enum=False, length=20), nullable=False),
    sa.Column('status', sa.Enum('DRAFT', 'READY', 'SENT_MANUALLY', 'CANCELLED', name='outreachstatus', native_enum=False, length=20), nullable=False),
    sa.Column('subject', sa.String(length=300), nullable=True),
    sa.Column('message', sa.String(length=4000), nullable=True),
    sa.Column('rationale', sa.String(length=2000), nullable=True),
    sa.Column('evidence_ids', sa.JSON(), nullable=False),
    sa.Column('generated_by_ai', sa.Boolean(), nullable=False),
    sa.Column('provider', sa.String(length=40), nullable=True),
    sa.Column('model', sa.String(length=80), nullable=True),
    sa.Column('prompt_version', sa.String(length=10), nullable=False),
    sa.Column('duration_ms', sa.Float(), nullable=True),
    sa.Column('input_tokens', sa.Integer(), nullable=True),
    sa.Column('output_tokens', sa.Integer(), nullable=True),
    sa.Column('created_by', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['opportunity_id'], ['opportunities.id'], name=op.f('fk_outreach_messages_opportunity_id_opportunities')),
    sa.ForeignKeyConstraint(['contact_id'], ['contacts.id'], name=op.f('fk_outreach_messages_contact_id_contacts')),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_outreach_messages_created_by_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_outreach_messages'))
    )
    op.create_index(op.f('ix_outreach_messages_opportunity_id'), 'outreach_messages', ['opportunity_id'], unique=False)
    op.create_index(op.f('ix_outreach_messages_contact_id'), 'outreach_messages', ['contact_id'], unique=False)
    op.create_index(op.f('ix_outreach_messages_created_by'), 'outreach_messages', ['created_by'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_outreach_messages_created_by'), table_name='outreach_messages')
    op.drop_index(op.f('ix_outreach_messages_contact_id'), table_name='outreach_messages')
    op.drop_index(op.f('ix_outreach_messages_opportunity_id'), table_name='outreach_messages')
    op.drop_table('outreach_messages')
