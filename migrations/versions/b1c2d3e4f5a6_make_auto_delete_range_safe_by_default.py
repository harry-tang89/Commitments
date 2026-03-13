"""make auto delete range safe by default

Revision ID: b1c2d3e4f5a6
Revises: a1b2c3d4e5f6
Create Date: 2026-03-13 06:05:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "b1c2d3e4f5a6"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        sa.text(
            """
            UPDATE "user"
            SET setting_auto_delete_overdue_range = 'yesterday'
            WHERE setting_auto_delete_overdue = false
              AND setting_auto_delete_overdue_range = 'all'
            """
        )
    )

    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.alter_column(
            "setting_auto_delete_overdue_range",
            existing_type=sa.String(length=16),
            server_default="yesterday",
        )


def downgrade():
    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.alter_column(
            "setting_auto_delete_overdue_range",
            existing_type=sa.String(length=16),
            server_default="all",
        )
