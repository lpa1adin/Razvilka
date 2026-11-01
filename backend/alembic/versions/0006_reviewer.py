"""reviewer

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-31 19:00:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('review_rule_sets',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('rules', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('note', sa.String(length=500), nullable=False),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('version')
    )
    op.create_table('reviews',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('kind', sa.Enum('learner', 'reference', name='review_kind'), nullable=False),
    sa.Column('status', sa.Enum('queued', 'running', 'done', 'failed', name='review_status'), nullable=False),
    sa.Column('requested_by', sa.Integer(), nullable=True),
    sa.Column('task_id', sa.Integer(), nullable=True),
    sa.Column('task_version', sa.Integer(), nullable=True),
    sa.Column('spec_hash', sa.String(length=64), nullable=True),
    sa.Column('title', sa.String(length=300), nullable=False),
    sa.Column('statement', sa.Text(), nullable=False),
    sa.Column('files', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('rules_version', sa.Integer(), nullable=False),
    sa.Column('verdict', sa.String(length=30), nullable=True),
    sa.Column('findings', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('dropped', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('tokens', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('accepted_by', sa.Integer(), nullable=True),
    sa.Column('accepted_note', sa.String(length=500), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['accepted_by'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['requested_by'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_reviews_requested_by', 'reviews', ['requested_by'])
    op.create_index('ix_reviews_task_id', 'reviews', ['task_id'])


def downgrade() -> None:
    op.drop_table('reviews')
    op.drop_table('review_rule_sets')
    for name in ('review_status', 'review_kind'):
        sa.Enum(name=name).drop(op.get_bind(), checkfirst=True)
