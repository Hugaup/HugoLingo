from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models import Language, User, VocabItem, VocabReview
from app.schemas import (
    VocabBrowseItem,
    VocabCheckRequest,
    VocabCheckResponse,
    VocabOverview,
    VocabSessionItem,
)
from app.services import vocabulary
from app.services.grading import Grade

router = APIRouter(prefix="/vocab", tags=["vocabulary"])

Kind = Literal["word", "phrase"]


@router.get("/{language}/overview", response_model=VocabOverview)
async def overview(
    language: Language,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await vocabulary.overview(db, user.id, language, datetime.now(timezone.utc))


@router.get("/{language}/session", response_model=list[VocabSessionItem])
async def session(
    language: Language,
    kind: Kind | None = None,
    topic: str | None = Query(None, max_length=32),
    count: int = Query(10, ge=1, le=30),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await vocabulary.build_session(db, user.id, language, kind, topic, count, datetime.now(timezone.utc))


@router.get("/{language}/items", response_model=list[VocabBrowseItem])
async def items(
    language: Language,
    kind: Kind | None = None,
    topic: str | None = Query(None, max_length=32),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(VocabItem, VocabReview.box)
        .outerjoin(VocabReview, (VocabReview.item_id == VocabItem.id) & (VocabReview.user_id == user.id))
        .where(VocabItem.language == language)
        .order_by(VocabItem.topic, VocabItem.level, VocabItem.frequency_rank.nulls_last(), VocabItem.id)
    )
    if kind:
        query = query.where(VocabItem.kind == kind)
    if topic:
        query = query.where(VocabItem.topic == topic)
    return [{**vocabulary.item_dict(item), "box": box} for item, box in (await db.execute(query)).all()]


@router.post("/check", response_model=VocabCheckResponse)
async def check(
    req: VocabCheckRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    item = await db.get(VocabItem, req.item_id)
    if item is None:
        raise HTTPException(404, "No such vocabulary item")

    accepted = vocabulary.accepted_answers(item, req.exercise)
    if req.exercise == "flashcard":
        if req.knew is None:
            raise HTTPException(422, "Flashcards need 'knew': true or false")
        graded, answer = Grade("correct" if req.knew else "wrong"), ("knew it" if req.knew else "didn't know")
    else:
        graded, accepted = vocabulary.grade_answer(item, req.exercise, req.answer)
        answer = req.answer
        if req.exercise.startswith("choice_") and graded.is_almost:
            graded = Grade("wrong")  # picking an option is right or wrong, never "almost"

    review = await vocabulary.record(db, user.id, item, req.exercise, answer, graded.is_correct, graded.is_almost)
    return VocabCheckResponse(
        is_correct=graded.is_correct,
        result=graded.result,
        expected=accepted[0],
        accepted=accepted,
        box=review.box,
    )
