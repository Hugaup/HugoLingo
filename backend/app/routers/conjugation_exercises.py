from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models import User
from app.services.history import AttemptIn, record_attempts
from app.schemas import (
    SentenceGenerateRequest,
    SentenceExerciseItem,
    SentenceCheckRequest,
    SentenceCheckResponse,
)
from app.services.conjugation_utils import tense_table
from app.services.explain import explain_mistake, tense_name
from app.services.grading import grade
from app.services import sentence_pool
from app.services.sentences import NoConjugationData, generate_one

router = APIRouter(prefix="/conjugation-exercises", tags=["conjugation-exercises"])

# Forms that are genuinely interchangeable (e.g. haber 3s presente: "hay" vs "ha")
_ALTERNATES: dict[str, list[str]] = {
    "hay": ["ha"],
    "ha":  ["hay"],
}


@router.post("/sentence/generate", response_model=list[SentenceExerciseItem])
async def generate_sentences(req: SentenceGenerateRequest, db: AsyncSession = Depends(get_db)):
    sentence_pool.note_request(req.language, req.tenses)
    # Ready-made sentences first (instant), then live generation for the rest
    exercises: list[SentenceExerciseItem] = await sentence_pool.take(db, req.language, req.tenses, req.count)
    attempts = 0
    with sentence_pool.live_request():
        while len(exercises) < req.count and attempts < req.count * 8:
            attempts += 1
            try:
                item = await generate_one(db, req.language, req.tenses)
            except NoConjugationData:
                raise HTTPException(400, "No conjugation data found for the requested tenses")
            if item is not None:
                exercises.append(item)

    if not exercises:
        raise HTTPException(502, "Could not generate exercises — LLM returned invalid responses")

    sentence_pool.schedule_refill(req.language)
    return exercises


@router.post("/sentence/check", response_model=SentenceCheckResponse)
async def check_sentence(
    req: SentenceCheckRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    item = req.item
    accepted = [item.correct_form, *item.alternates, *_ALTERNATES.get(item.correct_form.strip().lower(), [])]
    form_grade = grade(req.user_form, accepted)
    form_correct = form_grade.is_correct
    tense_correct = (
        req.user_mood.lower() == item.mood.lower()
        and req.user_tense.lower() == item.tense.lower()
    )

    # Record before the LLM call so a slow/failed explanation doesn't lose the answer.
    # Naming the wrong tense counts as a miss too: it's the tense the user struggled with.
    await record_attempts(db, user.id, req.language, "sentence", [AttemptIn(
        verb_infinitive=item.verb_infinitive, mood=item.mood, tense=item.tense,
        person=item.person, user_answer=req.user_form, expected=item.correct_form,
        is_correct=form_correct and tense_correct, is_almost=form_grade.is_almost,
    )])

    # Instant one-line feedback. The LLM's longer explanation is no longer part of
    # the check (it took ~10 s); the frontend streams it from /chat/stream only
    # if the user opens "AI explanation".
    hint = None
    if not form_correct:
        hint = await explain_mistake(
            db, req.language, item.verb_infinitive, item.mood, item.tense, item.person,
            req.user_form, form_grade, item.correct_form,
        )
    elif not tense_correct:
        table = await tense_table(db, req.language, item.verb_infinitive, item.mood, item.tense)
        hint = {
            "summary": (
                f"Right form — but it's the {tense_name(item.mood, item.tense)}, "
                f"not the {tense_name(req.user_mood, req.user_tense)}."
            ),
            "mood": item.mood,
            "tense": item.tense,
            "forms": [{"person": p, "form": forms[0]} for p, forms in table.items()],
        }

    return SentenceCheckResponse(
        form_correct=form_correct,
        form_result=form_grade.result,
        tense_correct=tense_correct,
        hint=hint,
    )
