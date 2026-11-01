"""assessment: submissions and evaluator

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-31 22:00:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None

JSON = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    # Новый вид ревью — сданный проект. ADD VALUE нельзя внутри транзакции со своим использованием,
    # но здесь значение только добавляется
    op.execute("ALTER TYPE review_kind ADD VALUE IF NOT EXISTS 'project'")
    op.create_table('rubric_sets',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('criteria', JSON, nullable=False),
    sa.Column('mismatch_penalty', sa.Float(), nullable=False),
    sa.Column('note', sa.String(length=500), nullable=False),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('version')
    )
    op.create_table('reference_projects',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('url', sa.String(length=300), nullable=False),
    sa.Column('about', sa.Text(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('assignments',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('slug', sa.String(length=80), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('statement', sa.Text(), nullable=False),
    sa.Column('kind', sa.String(length=10), nullable=False),
    sa.Column('forks', JSON, nullable=False),
    sa.Column('tests', sa.Text(), nullable=False),
    sa.Column('reference_ids', JSON, nullable=False),
    sa.Column('threshold', sa.Float(), nullable=False),
    sa.Column('published', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('slug')
    )
    op.create_table('submissions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('assignment_id', sa.Integer(), nullable=False),
    sa.Column('attempt', sa.Integer(), nullable=False),
    sa.Column('source', sa.String(length=20), nullable=False),
    sa.Column('source_name', sa.String(length=300), nullable=False),
    sa.Column('files', JSON, nullable=False),
    sa.Column('vendor', JSON, nullable=False),
    sa.Column('warnings', JSON, nullable=False),
    sa.Column('answers', JSON, nullable=False),
    sa.Column('summary', sa.Text(), nullable=False),
    sa.Column('status', sa.Enum('testing', 'reviewing', 'evaluating', 'done', 'failed', name='submission_status'), nullable=False),
    sa.Column('steps', JSON, nullable=False),
    sa.Column('tests', JSON, nullable=True),
    sa.Column('review_id', sa.Integer(), nullable=True),
    sa.Column('rubric_version', sa.Integer(), nullable=False),
    sa.Column('evaluation', JSON, nullable=True),
    sa.Column('score', sa.Float(), nullable=True),
    sa.Column('passed', sa.Boolean(), nullable=True),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('tokens', JSON, nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['assignment_id'], ['assignments.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['review_id'], ['reviews.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_submissions_user_id', 'submissions', ['user_id'])
    op.create_index('ix_submissions_assignment_id', 'submissions', ['assignment_id'])


def downgrade() -> None:
    op.drop_table('submissions')
    op.drop_table('assignments')
    op.drop_table('reference_projects')
    op.drop_table('rubric_sets')
    sa.Enum(name='submission_status').drop(op.get_bind(), checkfirst=True)
