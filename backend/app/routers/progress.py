from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db
from app.dependencies import get_current_user
from app.models import Progress, Exercise, User
from app.schemas import ProgressStatsResponse

router = APIRouter(tags=["progress"])


@router.get("/progress", response_model=ProgressStatsResponse)
async def get_progress(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Progress, Exercise)
        .join(Exercise, Progress.exercise_id == Exercise.id)
        .where(Progress.user_id == user.id)
    )
    rows = result.all()

    if not rows:
        return ProgressStatsResponse(total=0, correct=0, accuracy=0.0, by_type={}, by_language={})

    total = len(rows)
    correct = sum(1 for p, _ in rows if p.is_correct)
    accuracy = round(correct / total * 100, 1)

    by_type: dict[str, dict] = {}
    by_language: dict[str, dict] = {}

    for progress, exercise in rows:
        t = exercise.type.value
        lang = exercise.language.value

        if t not in by_type:
            by_type[t] = {"total": 0, "correct": 0, "accuracy": 0.0}
        by_type[t]["total"] += 1
        if progress.is_correct:
            by_type[t]["correct"] += 1

        if lang not in by_language:
            by_language[lang] = {"total": 0, "correct": 0, "accuracy": 0.0}
        by_language[lang]["total"] += 1
        if progress.is_correct:
            by_language[lang]["correct"] += 1

    for stats in by_type.values():
        stats["accuracy"] = round(stats["correct"] / stats["total"] * 100, 1)
    for stats in by_language.values():
        stats["accuracy"] = round(stats["correct"] / stats["total"] * 100, 1)

    return ProgressStatsResponse(
        total=total,
        correct=correct,
        accuracy=accuracy,
        by_type=by_type,
        by_language=by_language,
    )
