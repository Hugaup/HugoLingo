import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models import User
from app.schemas import (
    ConversationCheckRequest,
    ConversationCheckResponse,
    ConversationReplyRequest,
    ConversationScenario,
    VerbMistake,
)
from app.services import conversation, sentence_pool
from app.services.llm import llm_client

router = APIRouter(prefix="/conversation", tags=["conversation"])

STREAM_ERROR = "\n\n[The AI is unavailable right now — is Ollama running?]"


def get_scenario(scenario_id: str) -> conversation.Scenario:
    scenario = conversation.SCENARIOS_BY_ID.get(scenario_id)
    if scenario is None:
        raise HTTPException(404, "No such scenario")
    return scenario


@router.get("/scenarios", response_model=list[ConversationScenario])
async def scenarios():
    return [ConversationScenario(id=s.id, title=s.title, description=s.description, goal=s.goal)
            for s in conversation.SCENARIOS]


@router.post("/reply")
async def reply(req: ConversationReplyRequest, user: User = Depends(get_current_user)):
    """The AI's next in-character line, sent as plain text while it's written
    (its opening line when there are no messages yet)."""
    scenario = get_scenario(req.scenario)
    messages = conversation.reply_messages(
        req.language, scenario, user.level, [m.model_dump() for m in req.messages],
    )

    async def chunks():
        with sentence_pool.live_request():
            try:
                async for text in llm_client.chat_stream(messages, max_tokens=200):
                    yield text
            except httpx.HTTPError:
                yield STREAM_ERROR

    return StreamingResponse(chunks(), media_type="text/plain; charset=utf-8")


@router.post("/check", response_model=ConversationCheckResponse)
async def check(
    req: ConversationCheckRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Check one learner message, record it, and return the correction (if any)."""
    get_scenario(req.scenario)
    message = req.message.strip()
    if not message:
        raise HTTPException(422, "Empty message")
    try:
        correction = await conversation.check_message(req.language, user.level, req.previous, message)
    except conversation.CheckFailed:
        raise HTTPException(502, "Couldn't check that message right now — is Ollama running?")
    turn = await conversation.record_turn(db, user.id, req.language, req.scenario, message, correction)
    return ConversationCheckResponse(
        result=turn.correction.result,
        corrected=turn.correction.corrected,
        explanation=turn.correction.explanation,
        verb_mistakes=[VerbMistake(verb=m.verb_infinitive, wrong=m.user_answer, right=m.expected)
                       for m in turn.verb_mistakes],
    )
