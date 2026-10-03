"""grammar_pool: pre-made, checked grammar-correction exercises

Revision ID: c9e1a3b5d7f8
Revises: b8d0f2a4c6e7
Create Date: 2026-10-03 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'c9e1a3b5d7f8'
down_revision: Union[str, Sequence[str], None] = 'b8d0f2a4c6e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Raw SQL so `language` reuses the existing enum type (see CLAUDE.md)
    op.execute("""
        CREATE TABLE grammar_pool (
            id                  SERIAL PRIMARY KEY,
            language            language     NOT NULL,
            level               INTEGER      NOT NULL,
            sentence_with_error VARCHAR(512) NOT NULL,
            corrected_sentence  VARCHAR(512) NOT NULL,
            error_type          VARCHAR(32)  NOT NULL,
            explanation         VARCHAR(500) NOT NULL,
            source              VARCHAR(16)  NOT NULL,
            model               VARCHAR(64)  NOT NULL,
            prompt_version      INTEGER      NOT NULL,
            created_at          TIMESTAMP WITH TIME ZONE NOT NULL
        )
    """)
    op.execute("CREATE INDEX ix_grammar_pool_language_level ON grammar_pool (language, level)")


def downgrade() -> None:
    op.execute("DROP TABLE grammar_pool")
