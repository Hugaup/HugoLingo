from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field
from app.models import ExerciseType, Language


class GenerateExerciseRequest(BaseModel):
    type: ExerciseType
    language: Language
    difficulty: int = 2


class ExerciseResponse(BaseModel):
    id: int
    type: ExerciseType
    language: Language
    difficulty: int
    content: dict


class CheckAnswerRequest(BaseModel):
    exercise_id: int
    user_answer: str


class CheckAnswerResponse(BaseModel):
    is_correct: bool
    explanation: str
    correct_answer: str


class ProgressStatsResponse(BaseModel):
    total: int
    correct: int
    accuracy: float
    by_type: dict[str, dict]
    by_language: dict[str, dict]


# ── Auth / users ──────────────────────────────────────────────────────────────

# Deliberately simple rules: the only password requirement is a minimum length.
USERNAME_PATTERN = r"^[A-Za-z0-9_.-]+$"
PASSWORD_MIN_LENGTH = 4


class SignupRequest(BaseModel):
    username: str = Field(min_length=3, max_length=32, pattern=USERNAME_PATTERN)
    password: str = Field(min_length=PASSWORD_MIN_LENGTH, max_length=128)


class LoginRequest(BaseModel):
    username: str
    password: str


class UserResponse(BaseModel):
    id: int
    username: str
    native_language: str
    target_language: Language | None
    level: int
    daily_goal: int


class UserSettingsUpdate(BaseModel):
    target_language: Language | None = None
    level: int | None = Field(default=None, ge=1, le=5)
    daily_goal: int | None = Field(default=None, ge=1, le=500)


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=PASSWORD_MIN_LENGTH, max_length=128)


# ── Chat ──────────────────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    messages: list[ChatMessage]

class ChatResponse(BaseModel):
    content: str


# ── Conjugation exercises ─────────────────────────────────────────────────────

class TenseFilter(BaseModel):
    mood: str
    tense: str

class SentenceGenerateRequest(BaseModel):
    language: Language
    tenses: list[TenseFilter] = []
    count: int = 3

class SentenceExerciseItem(BaseModel):
    sentence: str
    subject_hint: str
    verb_infinitive: str
    mood: str
    tense: str
    person: str
    correct_form: str
    alternates: list[str] = []

class SentenceCheckRequest(BaseModel):
    item: SentenceExerciseItem
    user_form: str
    user_mood: str
    user_tense: str
    language: Language

class SentenceCheckResponse(BaseModel):
    form_correct: bool
    tense_correct: bool
    explanation: str


# ── History / weak spots ──────────────────────────────────────────────────────

class AttemptRecord(BaseModel):
    verb_infinitive: str = Field(max_length=128)
    mood: str | None = Field(default=None, max_length=64)
    tense: str | None = Field(default=None, max_length=64)
    person: str | None = Field(default=None, max_length=32)
    user_answer: str = Field(max_length=512)
    expected: str = Field(max_length=512)
    is_correct: bool


class RecordAttemptsRequest(BaseModel):
    language: Language
    # Only practice areas graded in the browser report here; the others are
    # recorded server-side by their own check endpoints.
    source: Literal["verb_table"]
    attempts: list[AttemptRecord] = Field(max_length=300)


class WeakItem(BaseModel):
    verb_infinitive: str | None = None
    mood: str | None = None
    tense: str | None = None
    attempts: int
    mistakes: int
    weakness: float
    last_mistake_at: datetime | None


class WeakSpotsResponse(BaseModel):
    verbs: list[WeakItem]
    tenses: list[WeakItem]
    combos: list[WeakItem]
    due_count: int


class DrillPrompt(BaseModel):
    verb_infinitive: str
    mood: str
    tense: str
    person: str
    reason: Literal["due", "weak"]


class DrillCheckRequest(BaseModel):
    language: Language
    verb_infinitive: str = Field(max_length=128)
    mood: str = Field(max_length=64)
    tense: str = Field(max_length=64)
    person: str = Field(max_length=32)
    answer: str = Field(max_length=128)


class DrillCheckResponse(BaseModel):
    is_correct: bool
    expected: str
    alternates: list[str]


class DailyCount(BaseModel):
    date: date
    total: int
    correct: int


class StatsResponse(BaseModel):
    total: int
    correct: int
    accuracy: float
    today_count: int
    streak_days: int
    daily: list[DailyCount]


class GridCell(BaseModel):
    attempts: int
    correct: int


class GridRow(BaseModel):
    verb_infinitive: str
    cells: dict[str, GridCell]  # keyed "mood||tense"


class GridResponse(BaseModel):
    tenses: list[TenseFilter]
    rows: list[GridRow]
