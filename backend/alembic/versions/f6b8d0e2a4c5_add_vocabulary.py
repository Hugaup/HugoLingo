"""add vocabulary: vocab_items, vocab_reviews, vocab_attempts

Revision ID: f6b8d0e2a4c5
Revises: e5a7c9d1f3b4
Create Date: 2026-10-03 03:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'f6b8d0e2a4c5'
down_revision: Union[str, Sequence[str], None] = 'e5a7c9d1f3b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Raw SQL so `language` reuses the existing enum type (see CLAUDE.md)
    op.execute("""
        CREATE TABLE vocab_items (
            id                  SERIAL PRIMARY KEY,
            language            language     NOT NULL,
            kind                VARCHAR(16)  NOT NULL,
            text                VARCHAR(128) NOT NULL,
            article             VARCHAR(8),
            translation         VARCHAR(256) NOT NULL,
            pos                 VARCHAR(16),
            topic               VARCHAR(32)  NOT NULL,
            level               INTEGER      NOT NULL,
            frequency_rank      INTEGER,
            example             VARCHAR(512) NOT NULL,
            example_translation VARCHAR(512) NOT NULL,
            CONSTRAINT uq_vocab_item UNIQUE (language, kind, text)
        )
    """)
    op.execute("CREATE INDEX ix_vocab_items_language_topic ON vocab_items (language, topic)")

    op.execute("""
        CREATE TABLE vocab_reviews (
            id            SERIAL PRIMARY KEY,
            user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            item_id       INTEGER NOT NULL REFERENCES vocab_items(id) ON DELETE CASCADE,
            box           INTEGER NOT NULL,
            due_at        TIMESTAMP WITH TIME ZONE NOT NULL,
            last_seen_at  TIMESTAMP WITH TIME ZONE NOT NULL,
            correct_count INTEGER NOT NULL,
            wrong_count   INTEGER NOT NULL,
            CONSTRAINT uq_vocab_review UNIQUE (user_id, item_id)
        )
    """)
    op.execute("CREATE INDEX ix_vocab_reviews_user_due ON vocab_reviews (user_id, due_at)")

    op.execute("""
        CREATE TABLE vocab_attempts (
            id          SERIAL PRIMARY KEY,
            user_id     INTEGER      NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            item_id     INTEGER      NOT NULL REFERENCES vocab_items(id) ON DELETE CASCADE,
            exercise    VARCHAR(24)  NOT NULL,
            user_answer VARCHAR(256) NOT NULL,
            is_correct  BOOLEAN      NOT NULL,
            is_almost   BOOLEAN      NOT NULL,
            created_at  TIMESTAMP WITH TIME ZONE NOT NULL
        )
    """)
    op.execute("CREATE INDEX ix_vocab_attempts_user_created ON vocab_attempts (user_id, created_at)")


def downgrade() -> None:
    op.execute("DROP TABLE vocab_attempts")
    op.execute("DROP TABLE vocab_reviews")
    op.execute("DROP TABLE vocab_items")
