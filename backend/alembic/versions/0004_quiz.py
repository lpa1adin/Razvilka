"""quiz

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-31 11:04:10.778841
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('quiz_topics',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('slug', sa.String(length=80), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('published', sa.Boolean(), nullable=False),
    sa.Column('size', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('slug')
    )
    op.create_table('quiz_attempts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('topic_id', sa.Integer(), nullable=False),
    sa.Column('status', sa.Enum('in_progress', 'finished', name='quiz_attempt_status'), nullable=False),
    sa.Column('mistakes_only', sa.Boolean(), nullable=False),
    sa.Column('score', sa.Integer(), nullable=False),
    sa.Column('total', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['topic_id'], ['quiz_topics.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_quiz_attempts_topic_id'), 'quiz_attempts', ['topic_id'], unique=False)
    op.create_index(op.f('ix_quiz_attempts_user_id'), 'quiz_attempts', ['user_id'], unique=False)
    op.create_table('questions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('topic_id', sa.Integer(), nullable=False),
    sa.Column('type', sa.Enum('single', 'multiple', 'order', 'match', name='question_type'), nullable=False),
    sa.Column('prompt', sa.Text(), nullable=False),
    sa.Column('code', sa.Text(), nullable=False),
    sa.Column('code_lang', sa.String(length=20), nullable=False),
    sa.Column('options', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('answer', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('explanation', sa.Text(), nullable=False),
    sa.Column('fragment_id', sa.Integer(), nullable=True),
    sa.Column('subtopic', sa.String(length=120), nullable=False),
    sa.Column('difficulty', sa.Integer(), nullable=False),
    sa.Column('status', sa.Enum('draft', 'published', 'archived', name='question_status'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['fragment_id'], ['fragments.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['topic_id'], ['quiz_topics.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_questions_topic_id'), 'questions', ['topic_id'], unique=False)
    op.create_table('quiz_attempt_items',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('attempt_id', sa.Integer(), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('question_id', sa.Integer(), nullable=True),
    sa.Column('snapshot', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('response', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('correct', sa.Boolean(), nullable=True),
    sa.ForeignKeyConstraint(['attempt_id'], ['quiz_attempts.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['question_id'], ['questions.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('attempt_id', 'position')
    )
    op.create_index(op.f('ix_quiz_attempt_items_attempt_id'), 'quiz_attempt_items', ['attempt_id'], unique=False)
    op.create_index(op.f('ix_quiz_attempt_items_question_id'), 'quiz_attempt_items', ['question_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_quiz_attempt_items_question_id'), table_name='quiz_attempt_items')
    op.drop_index(op.f('ix_quiz_attempt_items_attempt_id'), table_name='quiz_attempt_items')
    op.drop_table('quiz_attempt_items')
    op.drop_index(op.f('ix_questions_topic_id'), table_name='questions')
    op.drop_table('questions')
    op.drop_index(op.f('ix_quiz_attempts_user_id'), table_name='quiz_attempts')
    op.drop_index(op.f('ix_quiz_attempts_topic_id'), table_name='quiz_attempts')
    op.drop_table('quiz_attempts')
    op.drop_table('quiz_topics')
    for name in ('question_type', 'question_status', 'quiz_attempt_status'):
        sa.Enum(name=name).drop(op.get_bind())
