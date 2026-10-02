from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.dependencies import get_current_user
from app.models import Exercise, Progress, User, ExerciseType
from app.schemas import GenerateExerciseRequest, ExerciseResponse, CheckAnswerRequest, CheckAnswerResponse
from app.services.exercise_gen import generate_exercise, CHECKERS, check_conjugation
from app.services.history import AttemptIn, record_attempts

router = APIRouter(prefix="/exercises", tags=["exercises"])


@router.post("/generate", response_model=ExerciseResponse)
async def generate(req: GenerateExerciseRequest, db: AsyncSession = Depends(get_db)):
    try:
        content = await generate_exercise(req.type, req.language, req.difficulty)
    except ValueError as e:
        raise HTTPException(status_code=502, detail=str(e))

    exercise = Exercise(
        type=req.type,
        language=req.language,
        difficulty=req.difficulty,
        content=content,
    )
    db.add(exercise)
    await db.commit()
    await db.refresh(exercise)
    return exercise


@router.post("/check", response_model=CheckAnswerResponse)
async def check(
    req: CheckAnswerRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    exercise = await db.get(Exercise, req.exercise_id)
    if not exercise:
        raise HTTPException(status_code=404, detail="Exercise not found")

    if exercise.type == ExerciseType.conjugation:
        is_correct, explanation = await check_conjugation(
            exercise.content, req.user_answer, db, exercise.language
        )
        verb = str(exercise.content.get("verb_infinitive", "")).strip()
        if verb:
            # The LLM's free-text tense name doesn't map onto DB tenses, so this
            # counts toward the verb's history only (mood/tense left empty).
            await record_attempts(db, user.id, exercise.language, "exercise", [AttemptIn(
                verb_infinitive=verb.lower(), mood=None, tense=None, person=None,
                user_answer=req.user_answer, expected=str(exercise.content.get("correct_answer", "")),
                is_correct=is_correct,
            )])
    else:
        checker = CHECKERS.get(exercise.type)
        if not checker:
            raise HTTPException(status_code=400, detail="Unknown exercise type")
        is_correct, explanation = checker(exercise.content, req.user_answer)
    correct_answer = _get_correct_answer(exercise)

    progress = Progress(
        user_id=user.id,
        exercise_id=exercise.id,
        user_answer=req.user_answer,
        is_correct=is_correct,
    )
    db.add(progress)
    await db.commit()

    return CheckAnswerResponse(
        is_correct=is_correct,
        explanation=explanation,
        correct_answer=correct_answer,
    )


def _get_correct_answer(exercise: Exercise) -> str:
    content = exercise.content
    if exercise.type.value == "conjugation":
        return content.get("correct_answer", "")
    if exercise.type.value == "grammar":
        return content.get("corrected_sentence", "")
    if exercise.type.value == "reading":
        questions = content.get("questions", [])
        return questions[0].get("correct_answer", "") if questions else ""
    return ""
