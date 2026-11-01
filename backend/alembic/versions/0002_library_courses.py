"""library courses

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-30 21:58:35.605056
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('courses',
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
    op.create_table('sources',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('slug', sa.String(length=64), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('author', sa.String(length=200), nullable=False),
    sa.Column('kind', sa.String(length=32), nullable=False),
    sa.Column('homepage', sa.String(length=300), nullable=False),
    sa.Column('license_name', sa.String(length=120), nullable=False),
    sa.Column('license_url', sa.String(length=300), nullable=False),
    sa.Column('license_mode', sa.Enum('full_text', 'reference', name='license_mode'), nullable=False),
    sa.Column('license_note', sa.Text(), nullable=False),
    sa.Column('license_hash', sa.String(length=64), nullable=True),
    sa.Column('license_status', sa.Enum('ok', 'needs_review', name='license_status'), nullable=False),
    sa.Column('last_commit', sa.String(length=40), nullable=True),
    sa.Column('last_commit_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_import_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('slug')
    )
    op.create_table('course_versions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('course_id', sa.Integer(), nullable=False),
    sa.Column('number', sa.Integer(), nullable=False),
    sa.Column('status', sa.Enum('draft', 'published', 'superseded', name='course_version_status'), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('content', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('change_note', sa.Text(), nullable=False),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('published_by', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['course_id'], ['courses.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['published_by'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('course_id', 'number')
    )
    op.create_index(op.f('ix_course_versions_course_id'), 'course_versions', ['course_id'], unique=False)
    op.create_table('enrollments',
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('course_id', sa.Integer(), nullable=False),
    sa.Column('version_number', sa.Integer(), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['course_id'], ['courses.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id', 'course_id')
    )
    op.create_table('fragments',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('source_id', sa.Integer(), nullable=False),
    sa.Column('external_id', sa.String(length=400), nullable=False),
    sa.Column('title', sa.String(length=300), nullable=False),
    sa.Column('section', sa.String(length=300), nullable=False),
    sa.Column('url', sa.String(length=500), nullable=False),
    sa.Column('content_html', sa.Text(), nullable=True),
    sa.Column('outline', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('excerpt', sa.Text(), nullable=False),
    sa.Column('plain_text', sa.Text(), nullable=False),
    sa.Column('search', postgresql.TSVECTOR(), sa.Computed("setweight(to_tsvector('russian', coalesce(title, '')), 'A') || setweight(to_tsvector('russian', coalesce(section, '')), 'B') || setweight(to_tsvector('russian', coalesce(plain_text, '')), 'C')", persisted=True), nullable=True),
    sa.Column('content_hash', sa.String(length=64), nullable=False),
    sa.Column('status', sa.Enum('active', 'removed', name='fragment_status'), nullable=False),
    sa.Column('needs_review', sa.Boolean(), nullable=False),
    sa.Column('source_commit', sa.String(length=40), nullable=False),
    sa.Column('imported_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('changed_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['source_id'], ['sources.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('source_id', 'external_id')
    )
    op.create_index('ix_fragments_search', 'fragments', ['search'], unique=False, postgresql_using='gin')
    op.create_index(op.f('ix_fragments_source_id'), 'fragments', ['source_id'], unique=False)
    op.create_table('import_runs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('source_id', sa.Integer(), nullable=False),
    sa.Column('status', sa.Enum('running', 'done', 'failed', name='import_run_status'), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('commit', sa.String(length=40), nullable=True),
    sa.Column('added', sa.Integer(), nullable=False),
    sa.Column('changed', sa.Integer(), nullable=False),
    sa.Column('removed', sa.Integer(), nullable=False),
    sa.Column('unchanged', sa.Integer(), nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['source_id'], ['sources.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_import_runs_source_id'), 'import_runs', ['source_id'], unique=False)
    op.create_table('lesson_progress',
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('course_id', sa.Integer(), nullable=False),
    sa.Column('lesson_id', sa.String(length=40), nullable=False),
    sa.Column('completed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['course_id'], ['courses.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id', 'course_id', 'lesson_id')
    )


def downgrade() -> None:
    op.drop_table('lesson_progress')
    op.drop_index(op.f('ix_import_runs_source_id'), table_name='import_runs')
    op.drop_table('import_runs')
    op.drop_index(op.f('ix_fragments_source_id'), table_name='fragments')
    op.drop_index('ix_fragments_search', table_name='fragments', postgresql_using='gin')
    op.drop_table('fragments')
    op.drop_table('enrollments')
    op.drop_index(op.f('ix_course_versions_course_id'), table_name='course_versions')
    op.drop_table('course_versions')
    op.drop_table('sources')
    op.drop_table('courses')
    # Enum-типы Postgres не удаляются вместе с таблицами.
    sa.Enum(name='license_mode').drop(op.get_bind())
    sa.Enum(name='license_status').drop(op.get_bind())
    sa.Enum(name='fragment_status').drop(op.get_bind())
    sa.Enum(name='import_run_status').drop(op.get_bind())
    sa.Enum(name='course_version_status').drop(op.get_bind())
