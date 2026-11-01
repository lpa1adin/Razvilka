"""task versions: proposed change to statement/starter/hints waiting for the admin

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-02 10:00:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0012'
down_revision = '0011'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('task_versions', sa.Column('proposal', postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    op.drop_column('task_versions', 'proposal')
