"""architecture trainer attempts

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-01 05:00:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0008'
down_revision = '0007'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('arch_attempts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('slug', sa.String(length=80), nullable=False),
    sa.Column('answer', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('result', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('score', sa.Float(), nullable=True),
    sa.Column('status', sa.String(length=12), nullable=False),
    sa.Column('error', sa.String(length=500), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_arch_attempts_user_id', 'arch_attempts', ['user_id'])
    op.create_index('ix_arch_attempts_slug', 'arch_attempts', ['slug'])


def downgrade() -> None:
    op.drop_table('arch_attempts')
