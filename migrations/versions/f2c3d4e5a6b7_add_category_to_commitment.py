"""add category to commitment

Revision ID: f2c3d4e5a6b7
Revises: e1b2c3d4f5a6
Create Date: 2026-02-28 12:20:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f2c3d4e5a6b7'
down_revision = 'e1b2c3d4f5a6'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('commitment', schema=None) as batch_op:
        batch_op.add_column(sa.Column('category', sa.String(length=32), nullable=True))
        batch_op.create_index(batch_op.f('ix_commitment_category'), ['category'], unique=False)


def downgrade():
    with op.batch_alter_table('commitment', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_commitment_category'))
        batch_op.drop_column('category')
