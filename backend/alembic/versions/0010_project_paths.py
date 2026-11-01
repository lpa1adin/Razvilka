"""project paths «напиши заново сам»

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-01 09:00:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0010'
down_revision = '0009'
branch_labels = None
depends_on = None

JSON = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.execute("ALTER TYPE gen_what ADD VALUE IF NOT EXISTS 'path'")
    op.create_table('project_paths',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('slug', sa.String(length=80), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('project', sa.String(length=200), nullable=False),
    sa.Column('kind', sa.String(length=10), nullable=False),
    sa.Column('roles', JSON, nullable=False),
    sa.Column('published', sa.Boolean(), nullable=False),
    sa.Column('gen_request_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['gen_request_id'], ['gen_requests.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('slug')
    )
    op.add_column('assignments', sa.Column('path_id', sa.Integer(), nullable=True))
    op.add_column('assignments', sa.Column('position', sa.Integer(), server_default='0', nullable=False))
    op.add_column('assignments', sa.Column('goal', sa.Text(), server_default='', nullable=False))
    op.add_column('assignments', sa.Column('files_hint', JSON, server_default='[]', nullable=False))
    op.add_column('assignments', sa.Column('fragment_ids', JSON, server_default='[]', nullable=False))
    op.add_column('assignments', sa.Column('check_status', sa.String(length=12), server_default='not_checked', nullable=False))
    op.add_column('assignments', sa.Column('check_report', JSON, nullable=True))
    op.create_foreign_key('fk_assignments_path', 'assignments', 'project_paths', ['path_id'], ['id'], ondelete='CASCADE')
    op.create_index('ix_assignments_path_id', 'assignments', ['path_id'])


def downgrade() -> None:
    op.drop_index('ix_assignments_path_id', 'assignments')
    op.drop_constraint('fk_assignments_path', 'assignments', type_='foreignkey')
    for col in ('check_report', 'check_status', 'fragment_ids', 'files_hint', 'goal', 'position', 'path_id'):
        op.drop_column('assignments', col)
    op.drop_table('project_paths')
