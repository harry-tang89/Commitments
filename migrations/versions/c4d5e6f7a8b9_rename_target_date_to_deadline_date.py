"""rename target_date to deadline_date on commitment

Revision ID: c4d5e6f7a8b9
Revises: 9a1b2c3d4e5f
Create Date: 2026-03-02 16:35:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c4d5e6f7a8b9"
down_revision = "9a1b2c3d4e5f"
branch_labels = None
depends_on = None


def _column_names(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {column["name"] for column in inspector.get_columns(table_name)}


def _index_names(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {index["name"] for index in inspector.get_indexes(table_name)}


def upgrade():
    columns = _column_names("commitment")
    if "target_date" in columns and "deadline_date" not in columns:
        with op.batch_alter_table("commitment", schema=None) as batch_op:
            batch_op.alter_column(
                "target_date",
                new_column_name="deadline_date",
                existing_type=sa.Date(),
                existing_nullable=False,
            )

    indexes = _index_names("commitment")
    if "ix_commitment_target_date" in indexes:
        op.drop_index("ix_commitment_target_date", table_name="commitment")

    indexes = _index_names("commitment")
    if "ix_commitment_deadline_date" not in indexes:
        op.create_index(
            "ix_commitment_deadline_date",
            "commitment",
            ["deadline_date"],
            unique=False,
        )


def downgrade():
    indexes = _index_names("commitment")
    if "ix_commitment_deadline_date" in indexes:
        op.drop_index("ix_commitment_deadline_date", table_name="commitment")

    columns = _column_names("commitment")
    if "deadline_date" in columns and "target_date" not in columns:
        with op.batch_alter_table("commitment", schema=None) as batch_op:
            batch_op.alter_column(
                "deadline_date",
                new_column_name="target_date",
                existing_type=sa.Date(),
                existing_nullable=False,
            )

    indexes = _index_names("commitment")
    if "ix_commitment_target_date" not in indexes:
        op.create_index(
            "ix_commitment_target_date",
            "commitment",
            ["target_date"],
            unique=False,
        )
