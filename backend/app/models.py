import enum
from datetime import datetime, timezone
from sqlalchemy import String, Integer, Float, Boolean, DateTime, ForeignKey, Enum, JSON, UniqueConstraint
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
    native_language: Mapped[str] = mapped_column(String(32), nullable=False, default="english")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    progress: Mapped[list["Progress"]] = relationship(back_populates="user")


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
