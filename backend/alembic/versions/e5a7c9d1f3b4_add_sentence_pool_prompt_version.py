"""add sentence_pool.prompt_version

Revision ID: e5a7c9d1f3b4
Revises: d4f6b8c0e2a3
Create Date: 2026-10-03 02:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5a7c9d1f3b4'
down_revision: Union[str, Sequence[str], None] = 'd4f6b8c0e2a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Existing rows were made by the version-1 prompt; they stop being served and
    # are cleared by the next background refill
    op.add_column("sentence_pool", sa.Column("prompt_version", sa.Integer(), nullable=False, server_default="1"))


def downgrade() -> None:
    op.drop_column("sentence_pool", "prompt_version")
