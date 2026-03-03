"""add invite code to commitment

Revision ID: d3bca5ce5f2f
Revises: 1d2cfa3e9b7c
Create Date: 2026-02-23 13:20:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd3bca5ce5f2f'
down_revision = '1d2cfa3e9b7c'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('commitment', schema=None) as batch_op:
        batch_op.add_column(sa.Column('invite_code', sa.String(length=8), nullable=True))
        batch_op.create_index(batch_op.f('ix_commitment_invite_code'), ['invite_code'], unique=True)


def downgrade():
    with op.batch_alter_table('commitment', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_commitment_invite_code'))
        batch_op.drop_column('invite_code')
