"""commitments table

Revision ID: 7f8c3b2fd4a1
Revises: 679a62aaa273
Create Date: 2026-02-15 16:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '7f8c3b2fd4a1'
down_revision = '679a62aaa273'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'commitment',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=140), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('target_date', sa.Date(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('commitment', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_commitment_target_date'), ['target_date'], unique=False)
        batch_op.create_index(batch_op.f('ix_commitment_user_id'), ['user_id'], unique=False)


def downgrade():
    with op.batch_alter_table('commitment', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_commitment_user_id'))
        batch_op.drop_index(batch_op.f('ix_commitment_target_date'))

    op.drop_table('commitment')
