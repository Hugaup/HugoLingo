import enum
from datetime import datetime, timezone
from sqlalchemy import String, Integer, Float, Boolean, DateTime, ForeignKey, Enum, JSON, UniqueConstraint, Index
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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    __table_args__ = (
        Index("ix_sentence_pool_language_tense", "language", "mood", "tense"),
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
