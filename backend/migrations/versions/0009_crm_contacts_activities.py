"""crm contacts and activities

Revision ID: f7d3crm0009
Revises: f7c2crm0008
Create Date: 2026-09-07 00:10:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f7d3crm0009'
down_revision: str | None = 'f7c2crm0008'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('contacts',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('company_id', sa.Uuid(), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('role', sa.String(length=120), nullable=True),
    sa.Column('email', sa.String(length=255), nullable=True),
    sa.Column('phone', sa.String(length=50), nullable=True),
    sa.Column('source', sa.String(length=30), nullable=False),
    sa.Column('validation_status', sa.Enum('UNVERIFIED', 'VERIFIED', 'INVALID', name='contactvalidationstatus', native_enum=False, length=20), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['company_id'], ['companies.id'], name=op.f('fk_contacts_company_id_companies')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_contacts'))
    )
    op.create_index(op.f('ix_contacts_company_id'), 'contacts', ['company_id'], unique=False)

    op.create_table('activities',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('opportunity_id', sa.Uuid(), nullable=False),
    sa.Column('type', sa.Enum('NOTE', 'TASK', 'CALL', 'MEETING', 'EMAIL', 'WHATSAPP', 'OUTREACH', 'STAGE_CHANGE', 'OWNERSHIP_CHANGED', 'SYSTEM', name='activitytype', native_enum=False, length=24), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=True),
    sa.Column('description', sa.String(length=4000), nullable=True),
    sa.Column('status', sa.Enum('OPEN', 'DONE', name='activitystatus', native_enum=False, length=10), nullable=True),
    sa.Column('due_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('context', sa.JSON(), nullable=True),
    sa.Column('created_by', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['opportunity_id'], ['opportunities.id'], name=op.f('fk_activities_opportunity_id_opportunities')),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_activities_created_by_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_activities'))
    )
    op.create_index(op.f('ix_activities_opportunity_id'), 'activities', ['opportunity_id'], unique=False)
    op.create_index(op.f('ix_activities_created_by'), 'activities', ['created_by'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_activities_created_by'), table_name='activities')
    op.drop_index(op.f('ix_activities_opportunity_id'), table_name='activities')
    op.drop_table('activities')
    op.drop_index(op.f('ix_contacts_company_id'), table_name='contacts')
    op.drop_table('contacts')
