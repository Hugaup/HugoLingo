from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db
from app.models import Progress, Exercise, User
from app.schemas import ProgressStatsResponse, UserCreate, UserResponse

router = APIRouter(tags=["progress"])


@router.post("/users", response_model=UserResponse, status_code=201)
async def create_user(req: UserCreate, db: AsyncSession = Depends(get_db)):
    user = User(username=req.username, native_language=req.native_language)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(user_id: int, db: AsyncSession = Depends(get_db)):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.get("/progress/{user_id}", response_model=ProgressStatsResponse)
async def get_progress(user_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Progress, Exercise)
        .join(Exercise, Progress.exercise_id == Exercise.id)
        .where(Progress.user_id == user_id)
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
