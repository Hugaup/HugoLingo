from pydantic import BaseModel
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
    user_id: int = 1


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


class UserCreate(BaseModel):
    username: str
    native_language: str = "english"


class UserResponse(BaseModel):
    id: int
    username: str
    native_language: str


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
