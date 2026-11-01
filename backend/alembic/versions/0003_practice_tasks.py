"""practice tasks

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-30 22:33:51.458645
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('tasks',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('slug', sa.String(length=80), nullable=False),
    sa.Column('published_version', sa.Integer(), nullable=True),
    sa.Column('draft_version', sa.Integer(), nullable=True),
    sa.Column('archived', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('slug')
    )
    op.create_table('task_attempts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('task_id', sa.Integer(), nullable=False),
    sa.Column('version_number', sa.Integer(), nullable=False),
    sa.Column('passed', sa.Boolean(), nullable=False),
    sa.Column('results', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('hints_used', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_task_attempts_task_id'), 'task_attempts', ['task_id'], unique=False)
    op.create_index(op.f('ix_task_attempts_user_id'), 'task_attempts', ['user_id'], unique=False)
    op.create_table('task_versions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('task_id', sa.Integer(), nullable=False),
    sa.Column('number', sa.Integer(), nullable=False),
    sa.Column('status', postgresql.ENUM('draft', 'published', 'superseded', name='course_version_status', create_type=False), nullable=False),
    sa.Column('spec', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('check_status', sa.Enum('not_checked', 'queued', 'passed', 'failed', name='task_check_status'), nullable=False),
    sa.Column('check_report', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('checked_hash', sa.String(length=64), nullable=True),
    sa.Column('change_note', sa.String(length=1500), nullable=False),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('task_id', 'number')
    )
    op.create_index(op.f('ix_task_versions_task_id'), 'task_versions', ['task_id'], unique=False)
    op.create_table('task_work',
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('task_id', sa.Integer(), nullable=False),
    sa.Column('version_number', sa.Integer(), nullable=False),
    sa.Column('files', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('hints_used', sa.Integer(), nullable=False),
    sa.Column('solved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id', 'task_id')
    )


def downgrade() -> None:
    op.drop_table('task_work')
    op.drop_index(op.f('ix_task_versions_task_id'), table_name='task_versions')
    op.drop_table('task_versions')
    op.drop_index(op.f('ix_task_attempts_user_id'), table_name='task_attempts')
    op.drop_index(op.f('ix_task_attempts_task_id'), table_name='task_attempts')
    op.drop_table('task_attempts')
    op.drop_table('tasks')
    sa.Enum(name='task_check_status').drop(op.get_bind())
