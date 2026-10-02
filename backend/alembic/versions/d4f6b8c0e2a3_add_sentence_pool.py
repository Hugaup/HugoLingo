"""add sentence_pool (pre-generated practice sentences)

Revision ID: d4f6b8c0e2a3
Revises: c3e5a7b9d1f2
Create Date: 2026-10-03 00:30:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'd4f6b8c0e2a3'
down_revision: Union[str, Sequence[str], None] = 'c3e5a7b9d1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Raw SQL so `language` reuses the existing enum type (see CLAUDE.md)
    op.execute("""
        CREATE TABLE sentence_pool (
            id              SERIAL PRIMARY KEY,
            language        language     NOT NULL,
            verb_infinitive VARCHAR(128) NOT NULL,
            mood            VARCHAR(64)  NOT NULL,
            tense           VARCHAR(64)  NOT NULL,
            person          VARCHAR(32)  NOT NULL,
            sentence        VARCHAR(512) NOT NULL,
            subject_hint    VARCHAR(128) NOT NULL,
            correct_form    VARCHAR(128) NOT NULL,
            alternates      JSON         NOT NULL,
            model           VARCHAR(64)  NOT NULL,
            created_at      TIMESTAMP WITH TIME ZONE NOT NULL
        )
    """)
    op.execute("CREATE INDEX ix_sentence_pool_language_tense ON sentence_pool (language, mood, tense)")


def downgrade() -> None:
    op.execute("DROP TABLE sentence_pool")
