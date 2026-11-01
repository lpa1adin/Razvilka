"""generation: pause and resume a draft

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-01 12:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = '0011'
down_revision = '0010'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Новое значение enum нельзя добавить внутри транзакции
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE gen_status ADD VALUE IF NOT EXISTS 'paused' BEFORE 'failed'")
    op.add_column('gen_requests', sa.Column('pause', sa.String(length=10), server_default='', nullable=False))


def downgrade() -> None:
    op.drop_column('gen_requests', 'pause')
    op.execute("UPDATE gen_requests SET status = 'failed' WHERE status = 'paused'")
