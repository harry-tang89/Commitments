"""add commitment collaborators

Revision ID: 1d2cfa3e9b7c
Revises: baee80779208
Create Date: 2026-02-23 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '1d2cfa3e9b7c'
down_revision = 'baee80779208'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'commitment_collaborator',
        sa.Column('commitment_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['commitment_id'], ['commitment.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('commitment_id', 'user_id'),
    )
    with op.batch_alter_table('commitment_collaborator', schema=None) as batch_op:
        batch_op.create_index('ix_commitment_collaborator_user_id', ['user_id'], unique=False)


def downgrade():
    with op.batch_alter_table('commitment_collaborator', schema=None) as batch_op:
        batch_op.drop_index('ix_commitment_collaborator_user_id')

    op.drop_table('commitment_collaborator')
