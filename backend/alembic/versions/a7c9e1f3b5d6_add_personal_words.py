"""personal vocabulary words (vocab_items.owner_id) and the word_lookups cache

Revision ID: a7c9e1f3b5d6
Revises: f6b8d0e2a4c5
Create Date: 2026-10-03 04:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'a7c9e1f3b5d6'
down_revision: Union[str, Sequence[str], None] = 'f6b8d0e2a4c5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE vocab_items ADD COLUMN owner_id INTEGER REFERENCES users(id) ON DELETE CASCADE")
    # Shared items stay unique per language; personal ones per user. A plain
    # UNIQUE that includes owner_id wouldn't work: NULLs never conflict.
    op.execute("ALTER TABLE vocab_items DROP CONSTRAINT uq_vocab_item")
    op.execute("CREATE UNIQUE INDEX uq_vocab_item_shared ON vocab_items (language, kind, text) WHERE owner_id IS NULL")
    op.execute("CREATE UNIQUE INDEX uq_vocab_item_personal ON vocab_items (owner_id, language, text) WHERE owner_id IS NOT NULL")

    # Raw SQL so `language` reuses the existing enum type (see CLAUDE.md)
    op.execute("""
        CREATE TABLE word_lookups (
            id          SERIAL PRIMARY KEY,
            language    language     NOT NULL,
            word        VARCHAR(128) NOT NULL,
            lemma       VARCHAR(128) NOT NULL,
            translation VARCHAR(256) NOT NULL,
            pos         VARCHAR(16),
            created_at  TIMESTAMP WITH TIME ZONE NOT NULL,
            CONSTRAINT uq_word_lookup UNIQUE (language, word)
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE word_lookups")
    op.execute("DELETE FROM vocab_items WHERE owner_id IS NOT NULL")
    op.execute("DROP INDEX uq_vocab_item_personal")
    op.execute("DROP INDEX uq_vocab_item_shared")
    op.execute("ALTER TABLE vocab_items ADD CONSTRAINT uq_vocab_item UNIQUE (language, kind, text)")
    op.execute("ALTER TABLE vocab_items DROP COLUMN owner_id")
