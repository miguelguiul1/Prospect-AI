"""prototype company link (Prompt 10)

`owner_id` (String, nunca preenchido em nenhuma fase — pré-datava a
autenticação real da Fase 7) é removido e substituído por `company_id`
(FK real para `companies.id`). NULLABLE de propósito: não há como derivar
uma empresa correta para protótipos criados antes desta migration a partir
de `owner_id` (que nunca guardou nada útil) — inventar uma seria pior que
deixar `NULL` e documentar a limitação (ver docstring de
`app/domains/prototypes/models.py`). Nenhum ambiente de produção jamais
rodou este projeto, então não há dado real em risco.

Revision ID: 0011prototypecompany
Revises: f7e4crm0010
Create Date: 2026-09-07 15:34:39.763991

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0011prototypecompany'
down_revision: str | None = 'f7e4crm0010'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # `batch_alter_table` (não `op.create_foreign_key` direto): SQLite não
    # suporta ALTER TABLE ... ADD CONSTRAINT — confirmado ao testar esta
    # migration de verdade (primeira vez que uma FK é adicionada a uma
    # tabela já existente neste projeto; toda FK anterior nasceu junto com
    # `create_table`). O modo batch usa a estratégia copy-and-move do
    # SQLite e é transparente em PostgreSQL (onde o ALTER direto já
    # funcionaria de qualquer forma).
    with op.batch_alter_table('prototypes') as batch_op:
        batch_op.add_column(sa.Column('company_id', sa.Uuid(), nullable=True))
        batch_op.drop_index(op.f('ix_prototypes_owner_id'))
        batch_op.create_index(op.f('ix_prototypes_company_id'), ['company_id'], unique=False)
        batch_op.create_foreign_key(
            op.f('fk_prototypes_company_id_companies'), 'companies', ['company_id'], ['id']
        )
        batch_op.drop_column('owner_id')


def downgrade() -> None:
    with op.batch_alter_table('prototypes') as batch_op:
        batch_op.add_column(sa.Column('owner_id', sa.VARCHAR(length=120), nullable=True))
        batch_op.drop_constraint(op.f('fk_prototypes_company_id_companies'), type_='foreignkey')
        batch_op.drop_index(op.f('ix_prototypes_company_id'))
        batch_op.create_index(op.f('ix_prototypes_owner_id'), ['owner_id'], unique=False)
        batch_op.drop_column('company_id')
