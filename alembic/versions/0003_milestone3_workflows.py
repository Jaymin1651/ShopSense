"""Milestone 3: workflow run history and analytics snapshots.

Revision ID: 0003
Revises: 0002

Like 0002, every step checks first: revision 0001 builds tables from the
current ORM metadata, so on a fresh database these already exist.
"""
import sqlalchemy as sa
from alembic import op

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def _has_table(name):
    return name in sa.inspect(op.get_bind()).get_table_names()


def upgrade():
    if not _has_table('workflow_runs'):
        op.create_table(
            'workflow_runs',
            sa.Column('id', sa.Integer, primary_key=True),
            sa.Column('job', sa.String(60), nullable=False),
            sa.Column('trigger', sa.String(20), nullable=False, server_default='schedule'),
            sa.Column('status', sa.String(20), nullable=False, server_default='running'),
            sa.Column('attempts', sa.Integer, nullable=False, server_default='1'),
            sa.Column('started_at', sa.DateTime(timezone=True)),
            sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('duration_ms', sa.Integer, nullable=True),
            sa.Column('message', sa.Text, nullable=False, server_default=''),
            sa.Column('metrics', sa.Text, nullable=False, server_default='{}'),
        )
        op.create_index('ix_workflow_runs_job', 'workflow_runs', ['job'])
        op.create_index('ix_workflow_runs_status', 'workflow_runs', ['status'])
        op.create_index('ix_workflow_runs_started_at', 'workflow_runs', ['started_at'])
    if not _has_table('analytics_snapshots'):
        op.create_table(
            'analytics_snapshots',
            sa.Column('id', sa.Integer, primary_key=True),
            sa.Column('name', sa.String(80), nullable=False),
            sa.Column('scope', sa.String(40), nullable=False, server_default='all'),
            sa.Column('data_version', sa.String(80), nullable=False),
            sa.Column('payload', sa.Text, nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True)),
        )
        op.create_index('ix_snapshot_name_scope', 'analytics_snapshots', ['name', 'scope'], unique=True)


def downgrade():
    op.drop_table('analytics_snapshots')
    op.drop_table('workflow_runs')
