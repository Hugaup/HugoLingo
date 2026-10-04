import enum
from datetime import datetime, timezone
from sqlalchemy import String, Integer, Float, Boolean, DateTime, ForeignKey, Enum, JSON, UniqueConstraint, Index
from sqlalchemy import text as sql_text  # VocabItem has a column named `text`
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class ExerciseType(str, enum.Enum):
    conjugation = "conjugation"
    grammar = "grammar"
    reading = "reading"


class Language(str, enum.Enum):
    french = "french"
    spanish = "spanish"
    english = "english"
    norwegian = "norwegian"
    galician = "galician"


def now_utc():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    # Nullable: users created before auth existed have no password until one is
    # set with scripts/set_password.py. verify_password() rejects None.
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    native_language: Mapped[str] = mapped_column(String(32), nullable=False, default="english")
    target_language: Mapped[Language | None] = mapped_column(Enum(Language), nullable=True)
    # Same 1–5 scale as Exercise.difficulty (A1–C1)
    level: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    daily_goal: Mapped[int] = mapped_column(Integer, nullable=False, default=20)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    progress: Mapped[list["Progress"]] = relationship(back_populates="user")
    sessions: Mapped[list["UserSession"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class UserSession(Base):
    __tablename__ = "user_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    user: Mapped["User"] = relationship(back_populates="sessions")


class Exercise(Base):
    __tablename__ = "exercises"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[ExerciseType] = mapped_column(Enum(ExerciseType), nullable=False)
    language: Mapped[Language] = mapped_column(Enum(Language), nullable=False)
    difficulty: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    content: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    progress: Mapped[list["Progress"]] = relationship(back_populates="exercise")


class Progress(Base):
    __tablename__ = "progress"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    exercise_id: Mapped[int] = mapped_column(ForeignKey("exercises.id"), nullable=False)
    user_answer: Mapped[str] = mapped_column(String(512), nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    user: Mapped["User"] = relationship(back_populates="progress")
    exercise: Mapped["Exercise"] = relationship(back_populates="progress")


class Attempt(Base):
    """One answer to one conjugation prompt, from any practice area.

    mood/tense are the DB's names (tense passed through canonical_tense) when the
    prompt came from verb_conjugations; both are NULL for the LLM-generated
    exercises.py flow, whose free-text tense names don't map onto the DB.
    """
    __tablename__ = "attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    language: Mapped[Language] = mapped_column(Enum(Language), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    verb_infinitive: Mapped[str] = mapped_column(String(128), nullable=False)
    mood: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tense: Mapped[str | None] = mapped_column(String(64), nullable=True)
    person: Mapped[str | None] = mapped_column(String(32), nullable=True)
    user_answer: Mapped[str] = mapped_column(String(512), nullable=False)
    expected: Mapped[str] = mapped_column(String(512), nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    # Accent-only slip: shown as "almost" but still counted as a mistake (is_correct False)
    is_almost: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    __table_args__ = (
        Index("ix_attempts_user_language_created", "user_id", "language", "created_at"),
    )


class ReviewItem(Base):
    """Spaced-repetition (Leitner box) state for one verb+tense, per user."""
    __tablename__ = "review_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    language: Mapped[Language] = mapped_column(Enum(Language), nullable=False)
    verb_infinitive: Mapped[str] = mapped_column(String(128), nullable=False)
    mood: Mapped[str] = mapped_column(String(64), nullable=False)
    tense: Mapped[str] = mapped_column(String(64), nullable=False)
    box: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    correct_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    wrong_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint("user_id", "language", "verb_infinitive", "mood", "tense", name="uq_review_item"),
        Index("ix_review_items_user_language_due", "user_id", "language", "due_at"),
    )


class SentencePoolItem(Base):
    """A pre-generated, already-validated fill-in-the-blank sentence waiting to be served.

    Filled in the background by services/sentence_pool.py so sentence practice
    starts instantly; each row is deleted when it's handed to a user.
    """
    __tablename__ = "sentence_pool"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    language: Mapped[Language] = mapped_column(Enum(Language), nullable=False)
    verb_infinitive: Mapped[str] = mapped_column(String(128), nullable=False)
    mood: Mapped[str] = mapped_column(String(64), nullable=False)
    tense: Mapped[str] = mapped_column(String(64), nullable=False)  # canonical_tense()
    person: Mapped[str] = mapped_column(String(32), nullable=False)
    sentence: Mapped[str] = mapped_column(String(512), nullable=False)
    subject_hint: Mapped[str] = mapped_column(String(128), nullable=False)
    correct_form: Mapped[str] = mapped_column(String(128), nullable=False)
    alternates: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    # services/sentences.SENTENCE_PROMPT_VERSION it was made with; older ones are never served
    prompt_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    __table_args__ = (
        Index("ix_sentence_pool_language_tense", "language", "mood", "tense"),
    )


class VocabItem(Base):
    """A word or everyday phrase to learn, seeded from data/vocabulary/{language}.json."""
    __tablename__ = "vocab_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    language: Mapped[Language] = mapped_column(Enum(Language), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # "word" | "phrase"
    text: Mapped[str] = mapped_column(String(128), nullable=False)
    article: Mapped[str | None] = mapped_column(String(8), nullable=True)  # nouns: "el", "la", "l'"…
    translation: Mapped[str] = mapped_column(String(256), nullable=False)  # alternatives separated by ";"
    pos: Mapped[str | None] = mapped_column(String(16), nullable=True)
    topic: Mapped[str] = mapped_column(String(32), nullable=False)
    level: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-5, from frequency rank
    frequency_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    example: Mapped[str] = mapped_column(String(512), nullable=False)
    example_translation: Mapped[str] = mapped_column(String(512), nullable=False)
    # NULL = shared, curated item; set = a word one user saved while reading (kind "personal")
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True)

    __table_args__ = (
        Index("uq_vocab_item_shared", "language", "kind", "text", unique=True,
              postgresql_where=sql_text("owner_id IS NULL")),
        Index("uq_vocab_item_personal", "owner_id", "language", "text", unique=True,
              postgresql_where=sql_text("owner_id IS NOT NULL")),
        Index("ix_vocab_items_language_topic", "language", "topic"),
    )


class ConversationTurn(Base):
    """One message the learner sent in an AI conversation, and how the AI's check graded it.

    Counts toward the daily stats like any answer; verb mistakes found in it are
    also stored as `attempts` (source "conversation") so they feed weak spots.
    """
    __tablename__ = "conversation_turns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    language: Mapped[Language] = mapped_column(Enum(Language), nullable=False)
    scenario: Mapped[str] = mapped_column(String(32), nullable=False)
    message: Mapped[str] = mapped_column(String(1000), nullable=False)
    corrected: Mapped[str | None] = mapped_column(String(1000), nullable=True)  # NULL when it was right
    explanation: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    is_almost: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    __table_args__ = (
        Index("ix_conversation_turns_user_created", "user_id", "created_at"),
    )


class WordLookup(Base):
    """Cached AI dictionary answer for a word clicked while reading (one LLM call per word, ever)."""
    __tablename__ = "word_lookups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    language: Mapped[Language] = mapped_column(Enum(Language), nullable=False)
    word: Mapped[str] = mapped_column(String(128), nullable=False)  # as clicked, lowercased
    lemma: Mapped[str] = mapped_column(String(128), nullable=False)
    translation: Mapped[str] = mapped_column(String(256), nullable=False)
    pos: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    __table_args__ = (
        UniqueConstraint("language", "word", name="uq_word_lookup"),
    )


class VocabReview(Base):
    """Spaced-repetition (Leitner box) state for one vocabulary item, per user."""
    __tablename__ = "vocab_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    item_id: Mapped[int] = mapped_column(ForeignKey("vocab_items.id", ondelete="CASCADE"), nullable=False)
    box: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    correct_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    wrong_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint("user_id", "item_id", name="uq_vocab_review"),
        Index("ix_vocab_reviews_user_due", "user_id", "due_at"),
    )


class VocabAttempt(Base):
    """One answer to one vocabulary exercise."""
    __tablename__ = "vocab_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    item_id: Mapped[int] = mapped_column(ForeignKey("vocab_items.id", ondelete="CASCADE"), nullable=False)
    exercise: Mapped[str] = mapped_column(String(24), nullable=False)
    user_answer: Mapped[str] = mapped_column(String(256), nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    is_almost: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    __table_args__ = (
        Index("ix_vocab_attempts_user_created", "user_id", "created_at"),
    )


class GrammarAttempt(Base):
    """One answer to one grammar question (services/grammar_topics.py).

    `topic` + `question_id` point into the hand-written data in data/grammar/;
    the latest answer to each question is what sheet progress is computed from.
    """
    __tablename__ = "grammar_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    language: Mapped[Language] = mapped_column(Enum(Language), nullable=False)
    topic: Mapped[str] = mapped_column(String(64), nullable=False)
    question_id: Mapped[str] = mapped_column(String(32), nullable=False)
    user_answer: Mapped[str] = mapped_column(String(512), nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    is_almost: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    __table_args__ = (
        Index("ix_grammar_attempts_user_language_topic", "user_id", "language", "topic"),
        Index("ix_grammar_attempts_user_created", "user_id", "created_at"),
    )


class GrammarReview(Base):
    """Spaced-repetition (Leitner box) state for one grammar topic, per user.

    Only created by a mistake: a topic you've never got wrong has nothing to work on.
    """
    __tablename__ = "grammar_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    language: Mapped[Language] = mapped_column(Enum(Language), nullable=False)
    topic: Mapped[str] = mapped_column(String(64), nullable=False)
    box: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    correct_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    wrong_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint("user_id", "language", "topic", name="uq_grammar_review"),
        Index("ix_grammar_reviews_user_language_due", "user_id", "language", "due_at"),
    )


class VerbConjugation(Base):
    __tablename__ = "verb_conjugations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    language: Mapped[Language] = mapped_column(Enum(Language), nullable=False, index=True)
    verb_infinitive: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    mood: Mapped[str] = mapped_column(String(64), nullable=False)
    tense: Mapped[str] = mapped_column(String(64), nullable=False)
    person: Mapped[str] = mapped_column(String(32), nullable=False)
    form: Mapped[str] = mapped_column(String(128), nullable=False)

    __table_args__ = (
        UniqueConstraint("language", "verb_infinitive", "mood", "tense", "person", name="uq_verb_conjugation"),
    )
