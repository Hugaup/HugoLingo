import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.schemas import ChatRequest, ChatResponse
from app.services import sentence_pool
from app.services.llm import llm_client

router = APIRouter(tags=["chat"])

STREAM_ERROR = "\n\n[The AI is unavailable right now — is Ollama running?]"


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    messages = [{"role": m.role, "content": m.content} for m in req.messages]
    try:
        with sentence_pool.live_request():
            content = await llm_client.chat(messages)
    except httpx.HTTPError:
        raise HTTPException(502, "The AI is unavailable right now — is Ollama running?")
    return ChatResponse(content=content)


@router.post("/chat/stream")
async def chat_stream(req: ChatRequest):
    """Same as /chat, but sends the reply as plain text while it's being written."""
    messages = [{"role": m.role, "content": m.content} for m in req.messages]

    async def chunks():
        # Inside the generator so background refills stay paused for the whole stream
        with sentence_pool.live_request():
            try:
                async for text in llm_client.chat_stream(messages):
                    yield text
            except httpx.HTTPError:
                # Headers are already sent, so report the failure in-band
                yield STREAM_ERROR

    return StreamingResponse(chunks(), media_type="text/plain; charset=utf-8")
