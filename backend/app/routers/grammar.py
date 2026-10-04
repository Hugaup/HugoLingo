from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models import Language, User
from app.schemas import (
    GrammarAnswerRequest,
    GrammarAnswerResponse,
    GrammarFix,
    GrammarOverview,
    GrammarSheetOut,
    GrammarTopicDetail,
)
from app.services import grammar_topics

router = APIRouter(prefix="/grammar", tags=["grammar"])


def _topic(language: Language, topic_id: str) -> grammar_topics.Topic:
    topic = grammar_topics.get_topic(language, topic_id)
    if topic is None:
        raise HTTPException(404, "No such grammar topic")
    return topic


@router.get("/{language}", response_model=GrammarOverview)
async def overview(language: Language, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await grammar_topics.overview(db, user.id, language, datetime.now(timezone.utc))


@router.get("/{language}/topics/{topic_id}", response_model=GrammarTopicDetail)
async def topic(
    language: Language, topic_id: str,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    return await grammar_topics.topic_detail(db, user.id, language, _topic(language, topic_id), datetime.now(timezone.utc))


@router.get("/{language}/topics/{topic_id}/sheets/{number}", response_model=GrammarSheetOut)
async def sheet(language: Language, topic_id: str, number: int):
    t = _topic(language, topic_id)
    if not 1 <= number <= len(t.sheets):
        raise HTTPException(404, "No such sheet")
    s = t.sheets[number - 1]
    return GrammarSheetOut(
        topic=t.id, topic_title=t.title, number=s.number, title=s.title, sheet_count=len(t.sheets),
        questions=[grammar_topics.question_out(q) for q in s.questions],
    )


@router.get("/{language}/topics/{topic_id}/review", response_model=GrammarSheetOut)
async def review(
    language: Language, topic_id: str,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    """A review sheet: what you last got wrong first, then what you haven't tried."""
    t = _topic(language, topic_id)
    questions = await grammar_topics.review_questions(db, user.id, language, t)
    return GrammarSheetOut(
        topic=t.id, topic_title=t.title, number=None, title="Review", sheet_count=len(t.sheets),
        questions=[grammar_topics.question_out(q) for q in questions],
    )


@router.post("/answer", response_model=GrammarAnswerResponse)
async def answer(req: GrammarAnswerRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    t = _topic(req.language, req.topic)
    question = t.questions().get(req.question_id)
    if question is None:
        raise HTTPException(404, "No such question")
    if question.kind == "choice" and req.answer not in question.options:
        raise HTTPException(422, "Not one of the options")

    graded = await grammar_topics.grade_answer(db, req.language, question, req.answer)
    state = await grammar_topics.record_answer(
        db, user.id, req.language, t, question, req.answer, graded, datetime.now(timezone.utc),
    )
    return GrammarAnswerResponse(
        result=graded.result, is_correct=graded.result == "correct",
        answer=question.answer, sentence=question.filled(), explanation=graded.explanation,
        fix=GrammarFix(**vars(graded.fix)) if graded.fix else None,
        **state,
    )
