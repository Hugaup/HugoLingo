"""add verb_conjugations table

Revision ID: 7805ad5fd2c8
Revises: 1754923d9766
Create Date: 2026-06-12 16:44:46.146103

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7805ad5fd2c8'
down_revision: Union[str, Sequence[str], None] = '1754923d9766'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE verb_conjugations (
            id          SERIAL PRIMARY KEY,
            language    language     NOT NULL,
            verb_infinitive VARCHAR(128) NOT NULL,
            mood        VARCHAR(64)  NOT NULL,
            tense       VARCHAR(64)  NOT NULL,
            person      VARCHAR(32)  NOT NULL,
            form        VARCHAR(128) NOT NULL,
            CONSTRAINT uq_verb_conjugation
                UNIQUE (language, verb_infinitive, mood, tense, person)
        )
    """)
    op.execute("CREATE INDEX ix_verb_conjugations_language ON verb_conjugations (language)")
    op.execute("CREATE INDEX ix_verb_conjugations_verb_infinitive ON verb_conjugations (verb_infinitive)")


def downgrade() -> None:
    op.drop_table('verb_conjugations')
