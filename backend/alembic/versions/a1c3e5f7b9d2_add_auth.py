"""add auth: password + settings columns on users, user_sessions table

Revision ID: a1c3e5f7b9d2
Revises: 7805ad5fd2c8
Create Date: 2026-10-02 19:30:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'a1c3e5f7b9d2'
down_revision: Union[str, Sequence[str], None] = '7805ad5fd2c8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Raw SQL so target_language reuses the existing `language` enum
    # instead of autogenerate's failing CREATE TYPE (see CLAUDE.md).
    op.execute("""
        ALTER TABLE users
            ADD COLUMN password_hash   VARCHAR(255),
            ADD COLUMN target_language language,
            ADD COLUMN level           INTEGER NOT NULL DEFAULT 2,
            ADD COLUMN daily_goal      INTEGER NOT NULL DEFAULT 20
    """)
    op.execute("""
        CREATE TABLE user_sessions (
            id          SERIAL PRIMARY KEY,
            user_id     INTEGER     NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token_hash  VARCHAR(64) NOT NULL UNIQUE,
            created_at  TIMESTAMP WITH TIME ZONE NOT NULL,
            expires_at  TIMESTAMP WITH TIME ZONE NOT NULL
        )
    """)
    op.execute("CREATE INDEX ix_user_sessions_user_id ON user_sessions (user_id)")


def downgrade() -> None:
    op.execute("DROP TABLE user_sessions")
    op.execute("""
        ALTER TABLE users
            DROP COLUMN password_hash,
            DROP COLUMN target_language,
            DROP COLUMN level,
            DROP COLUMN daily_goal
    """)
