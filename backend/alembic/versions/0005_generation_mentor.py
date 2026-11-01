"""generation and mentor

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-31 15:00:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None

GEN_STATUS = ('proposed', 'new', 'planning', 'plan_ready', 'drafting', 'draft_ready', 'failed', 'rejected')


def upgrade() -> None:
    op.create_table('gen_requests',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('status', sa.Enum(*GEN_STATUS, name='gen_status'), nullable=False),
    sa.Column('what', sa.Enum('course', 'task', 'quiz', name='gen_what'), nullable=False),
    sa.Column('origin', sa.String(length=10), nullable=False),
    sa.Column('project', sa.String(length=200), nullable=False),
    sa.Column('focus', sa.String(length=300), nullable=False),
    sa.Column('topic', sa.String(length=300), nullable=False),
    sa.Column('level', sa.Integer(), nullable=False),
    sa.Column('notes', sa.Text(), nullable=False),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('plan', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('steps', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('result', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('mentor_threads',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('context_kind', sa.String(length=10), nullable=False),
    sa.Column('context_ref', sa.String(length=200), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'context_kind', 'context_ref')
    )
    op.create_index('ix_mentor_threads_user_id', 'mentor_threads', ['user_id'])
    op.create_table('mentor_messages',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('thread_id', sa.Integer(), nullable=False),
    sa.Column('role', sa.String(length=10), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('status', sa.Enum('pending', 'streaming', 'done', 'failed', name='mentor_message_status'), nullable=False),
    sa.Column('hint', sa.Boolean(), nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['thread_id'], ['mentor_threads.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_mentor_messages_thread_id', 'mentor_messages', ['thread_id'])
    op.add_column('task_work', sa.Column('mentor_hints', sa.Integer(), server_default='0', nullable=False))
    op.add_column('task_attempts', sa.Column('mentor_hints', sa.Integer(), server_default='0', nullable=False))


def downgrade() -> None:
    op.drop_column('task_attempts', 'mentor_hints')
    op.drop_column('task_work', 'mentor_hints')
    op.drop_table('mentor_messages')
    op.drop_table('mentor_threads')
    op.drop_table('gen_requests')
    for name in ('mentor_message_status', 'gen_what', 'gen_status'):
        sa.Enum(name=name).drop(op.get_bind(), checkfirst=True)
