"""arch attempts: only the first answer counts

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-01 07:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = '0009'
down_revision = '0008'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('arch_attempts', sa.Column('counted', sa.Boolean(), server_default=sa.false(), nullable=False))
    # Уже сделанные попытки: засчитанной считаем первую по каждому заданию
    op.execute("""
        UPDATE arch_attempts SET counted = true
        WHERE id IN (SELECT min(id) FROM arch_attempts WHERE status = 'done' GROUP BY user_id, slug)
    """)


def downgrade() -> None:
    op.drop_column('arch_attempts', 'counted')
