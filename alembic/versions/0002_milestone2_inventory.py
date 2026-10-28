"""Milestone 2: warehouses, category hierarchy, lead times and unit cost.

Revision ID: 0002
Revises: 0001

Revision 0001 builds the schema from the current ORM metadata, so on a fresh
database these objects already exist. Every step therefore checks first,
which keeps the migration safe both for new installs and for databases that
were created before Milestone 2.
"""
import sqlalchemy as sa
from alembic import op

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def _has_table(name):
    return name in sa.inspect(op.get_bind()).get_table_names()


def _columns(table):
    return {c['name'] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade():
    if not _has_table('warehouses'):
        op.create_table(
            'warehouses',
            sa.Column('id', sa.Integer, primary_key=True),
            sa.Column('name', sa.String(120), nullable=False, unique=True),
            sa.Column('location', sa.String(200), nullable=False, server_default=''),
            sa.Column('created_at', sa.DateTime(timezone=True)),
        )
    if not _has_table('categories'):
        op.create_table(
            'categories',
            sa.Column('id', sa.Integer, primary_key=True),
            sa.Column('name', sa.String(100), nullable=False, unique=True),
            sa.Column('parent_id', sa.Integer, sa.ForeignKey('categories.id'), nullable=True),
        )
        op.create_index('ix_categories_name', 'categories', ['name'])
    inventory = _columns('inventory')
    with op.batch_alter_table('inventory') as batch:
        if 'warehouse_id' not in inventory:
            batch.add_column(sa.Column('warehouse_id', sa.Integer, nullable=True))
            batch.create_foreign_key('fk_inventory_warehouse', 'warehouses', ['warehouse_id'], ['id'])
        if 'lead_time_days' not in inventory:
            batch.add_column(sa.Column('lead_time_days', sa.Integer, nullable=False, server_default='7'))
        if 'last_updated' not in inventory:
            batch.add_column(sa.Column('last_updated', sa.DateTime(timezone=True), nullable=True))
    if 'unit_cost' not in _columns('products'):
        with op.batch_alter_table('products') as batch:
            batch.add_column(sa.Column('unit_cost', sa.Numeric(12, 2), nullable=True))


def downgrade():
    with op.batch_alter_table('products') as batch:
        batch.drop_column('unit_cost')
    with op.batch_alter_table('inventory') as batch:
        batch.drop_column('last_updated')
        batch.drop_column('lead_time_days')
        batch.drop_column('warehouse_id')
    op.drop_table('categories')
    op.drop_table('warehouses')
