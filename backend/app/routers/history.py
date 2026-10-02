from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models import Language, User
from app.schemas import (
    DrillCheckRequest,
    DrillCheckResponse,
    DrillPrompt,
    GridResponse,
    RecordAttemptsRequest,
    StatsResponse,
    WeakSpotsResponse,
)
from app.services import history
from app.services.conjugation_utils import expected_forms
from app.services.explain import explain_mistake
from app.services.grading import grade

router = APIRouter(prefix="/history", tags=["history"])


@router.post("/attempts", status_code=204)
async def record_attempts(
    req: RecordAttemptsRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await history.record_attempts(
        db, user.id, req.language, req.source,
        [history.AttemptIn(**a.model_dump()) for a in req.attempts],
    )


@router.get("/weak-spots/{language}", response_model=WeakSpotsResponse)
async def weak_spots(
    language: Language,
    limit: int = Query(8, ge=1, le=50),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await history.weak_spots(db, user.id, language, limit, datetime.now(timezone.utc))


@router.get("/drill/{language}", response_model=list[DrillPrompt])
async def drill(
    language: Language,
    count: int = Query(10, ge=1, le=50),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await history.drill_prompts(db, user.id, language, count, datetime.now(timezone.utc))


@router.post("/drill/check", response_model=DrillCheckResponse)
async def drill_check(
    req: DrillCheckRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    forms = await expected_forms(db, req.language, req.verb_infinitive, req.mood, req.tense, req.person)
    if not forms:
        raise HTTPException(404, "No such conjugation")

    graded = grade(req.answer, forms)
    await history.record_attempts(db, user.id, req.language, "drill", [history.AttemptIn(
        verb_infinitive=req.verb_infinitive, mood=req.mood, tense=req.tense, person=req.person,
        user_answer=req.answer, expected=forms[0], is_correct=graded.is_correct, is_almost=graded.is_almost,
    )])
    explanation = None if graded.is_correct else await explain_mistake(
        db, req.language, req.verb_infinitive, req.mood, req.tense, req.person, req.answer, graded, forms[0],
    )
    return DrillCheckResponse(
        is_correct=graded.is_correct, result=graded.result,
        expected=forms[0], alternates=forms[1:], explanation=explanation,
    )


@router.get("/stats", response_model=StatsResponse)
async def stats(
    language: Language | None = None,
    tz: str = Query("UTC", max_length=64),
    days: int = Query(30, ge=1, le=366),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await history.stats(db, user.id, language, tz, days, datetime.now(timezone.utc))


@router.get("/grid/{language}", response_model=GridResponse)
async def grid(
    language: Language,
    verbs: int = Query(12, ge=1, le=50),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await history.grid(db, user.id, language, verbs)
