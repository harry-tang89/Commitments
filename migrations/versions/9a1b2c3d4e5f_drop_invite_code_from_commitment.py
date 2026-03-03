"""drop invite code from commitment

Revision ID: 9a1b2c3d4e5f
Revises: f2c3d4e5a6b7
Create Date: 2026-02-28 14:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "9a1b2c3d4e5f"
down_revision = "f2c3d4e5a6b7"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("commitment", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_commitment_invite_code"))
        batch_op.drop_column("invite_code")


def downgrade():
    with op.batch_alter_table("commitment", schema=None) as batch_op:
        batch_op.add_column(sa.Column("invite_code", sa.String(length=8), nullable=True))
        batch_op.create_index(batch_op.f("ix_commitment_invite_code"), ["invite_code"], unique=True)
