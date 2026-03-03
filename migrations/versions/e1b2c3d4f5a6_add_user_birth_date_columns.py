"""add user birth date columns

Revision ID: e1b2c3d4f5a6
Revises: d3bca5ce5f2f
Create Date: 2026-02-28 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e1b2c3d4f5a6'
down_revision = 'd3bca5ce5f2f'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.add_column(sa.Column('birth_day', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('birth_month', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('birth_year', sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_column('birth_year')
        batch_op.drop_column('birth_month')
        batch_op.drop_column('birth_day')
