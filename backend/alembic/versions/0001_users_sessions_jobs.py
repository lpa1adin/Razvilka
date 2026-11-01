"""users sessions jobs

Revision ID: 0001
Revises: 
Create Date: 2026-10-30 21:02:23.541699
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('jobs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('kind', sa.String(length=32), nullable=False),
    sa.Column('status', sa.Enum('queued', 'running', 'done', 'failed', name='job_status'), nullable=False),
    sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('result', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_jobs_pick', 'jobs', ['kind', 'status', 'created_at'], unique=False)
    op.create_table('users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('login', sa.String(length=64), nullable=False),
    sa.Column('display_name', sa.String(length=120), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('role', sa.Enum('user', 'admin', name='user_role'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('login')
    )
    op.create_table('worker_heartbeats',
    sa.Column('worker', sa.String(length=32), nullable=False),
    sa.Column('seen_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('worker')
    )
    op.create_table('sessions',
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('token_hash')
    )
    op.create_index(op.f('ix_sessions_user_id'), 'sessions', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_sessions_user_id'), table_name='sessions')
    op.drop_table('sessions')
    op.drop_table('worker_heartbeats')
    op.drop_table('users')
    op.drop_index('ix_jobs_pick', table_name='jobs')
    op.drop_table('jobs')
    # Enum-типы Postgres не удаляются вместе с таблицами.
    sa.Enum(name='user_role').drop(op.get_bind())
    sa.Enum(name='job_status').drop(op.get_bind())
