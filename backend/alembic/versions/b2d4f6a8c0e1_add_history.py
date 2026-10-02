"""add answer history: attempts and review_items tables

Revision ID: b2d4f6a8c0e1
Revises: a1c3e5f7b9d2
Create Date: 2026-10-02 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'b2d4f6a8c0e1'
down_revision: Union[str, Sequence[str], None] = 'a1c3e5f7b9d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Raw SQL so the language columns reuse the existing `language` enum (see CLAUDE.md)
    op.execute("""
        CREATE TABLE attempts (
            id              SERIAL PRIMARY KEY,
            user_id         INTEGER      NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            language        language     NOT NULL,
            source          VARCHAR(32)  NOT NULL,
            verb_infinitive VARCHAR(128) NOT NULL,
            mood            VARCHAR(64),
            tense           VARCHAR(64),
            person          VARCHAR(32),
            user_answer     VARCHAR(512) NOT NULL,
            expected        VARCHAR(512) NOT NULL,
            is_correct      BOOLEAN      NOT NULL,
            created_at      TIMESTAMP WITH TIME ZONE NOT NULL
        )
    """)
    op.execute("CREATE INDEX ix_attempts_user_language_created ON attempts (user_id, language, created_at)")

    op.execute("""
        CREATE TABLE review_items (
            id              SERIAL PRIMARY KEY,
            user_id         INTEGER      NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            language        language     NOT NULL,
            verb_infinitive VARCHAR(128) NOT NULL,
            mood            VARCHAR(64)  NOT NULL,
            tense           VARCHAR(64)  NOT NULL,
            box             INTEGER      NOT NULL,
            due_at          TIMESTAMP WITH TIME ZONE NOT NULL,
            last_seen_at    TIMESTAMP WITH TIME ZONE NOT NULL,
            correct_count   INTEGER      NOT NULL,
            wrong_count     INTEGER      NOT NULL,
            CONSTRAINT uq_review_item UNIQUE (user_id, language, verb_infinitive, mood, tense)
        )
    """)
    op.execute("CREATE INDEX ix_review_items_user_language_due ON review_items (user_id, language, due_at)")


def downgrade() -> None:
    op.execute("DROP TABLE review_items")
    op.execute("DROP TABLE attempts")
