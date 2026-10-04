"""grammar topics: answers and per-topic review boxes; drop grammar_pool

Grammar exercises are hand-written now (data/grammar/), so the stock of
LLM-made ones goes.

Revision ID: d1f3a5b7c9e0
Revises: c9e1a3b5d7f8
Create Date: 2026-10-04 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'd1f3a5b7c9e0'
down_revision: Union[str, Sequence[str], None] = 'c9e1a3b5d7f8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP TABLE grammar_pool")
    # Raw SQL so `language` reuses the existing enum type (see CLAUDE.md)
    op.execute("""
        CREATE TABLE grammar_attempts (
            id          SERIAL PRIMARY KEY,
            user_id     INTEGER      NOT NULL REFERENCES users (id) ON DELETE CASCADE,
            language    language     NOT NULL,
            topic       VARCHAR(64)  NOT NULL,
            question_id VARCHAR(32)  NOT NULL,
            user_answer VARCHAR(512) NOT NULL,
            is_correct  BOOLEAN      NOT NULL,
            is_almost   BOOLEAN      NOT NULL,
            created_at  TIMESTAMP WITH TIME ZONE NOT NULL
        )
    """)
    op.execute("CREATE INDEX ix_grammar_attempts_user_language_topic ON grammar_attempts (user_id, language, topic)")
    op.execute("CREATE INDEX ix_grammar_attempts_user_created ON grammar_attempts (user_id, created_at)")
    op.execute("""
        CREATE TABLE grammar_reviews (
            id            SERIAL PRIMARY KEY,
            user_id       INTEGER     NOT NULL REFERENCES users (id) ON DELETE CASCADE,
            language      language    NOT NULL,
            topic         VARCHAR(64) NOT NULL,
            box           INTEGER     NOT NULL,
            due_at        TIMESTAMP WITH TIME ZONE NOT NULL,
            last_seen_at  TIMESTAMP WITH TIME ZONE NOT NULL,
            correct_count INTEGER     NOT NULL,
            wrong_count   INTEGER     NOT NULL,
            CONSTRAINT uq_grammar_review UNIQUE (user_id, language, topic)
        )
    """)
    op.execute("CREATE INDEX ix_grammar_reviews_user_language_due ON grammar_reviews (user_id, language, due_at)")


def downgrade() -> None:
    op.execute("DROP TABLE grammar_reviews")
    op.execute("DROP TABLE grammar_attempts")
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
