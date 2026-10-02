"""conversation_turns: learner messages in AI conversations and their corrections

Revision ID: b8d0f2a4c6e7
Revises: a7c9e1f3b5d6
Create Date: 2026-10-03 06:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'b8d0f2a4c6e7'
down_revision: Union[str, Sequence[str], None] = 'a7c9e1f3b5d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Raw SQL so `language` reuses the existing enum type (see CLAUDE.md)
    op.execute("""
        CREATE TABLE conversation_turns (
            id          SERIAL PRIMARY KEY,
            user_id     INTEGER       NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            language    language      NOT NULL,
            scenario    VARCHAR(32)   NOT NULL,
            message     VARCHAR(1000) NOT NULL,
            corrected   VARCHAR(1000),
            explanation VARCHAR(500),
            is_correct  BOOLEAN       NOT NULL,
            is_almost   BOOLEAN       NOT NULL DEFAULT false,
            created_at  TIMESTAMP WITH TIME ZONE NOT NULL
        )
    """)
    op.execute("CREATE INDEX ix_conversation_turns_user_created ON conversation_turns (user_id, created_at)")


def downgrade() -> None:
    op.execute("DROP TABLE conversation_turns")
