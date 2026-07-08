from fastapi import APIRouter
from app.schemas import ChatRequest, ChatResponse
from app.services.llm import llm_client

router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    messages = [{"role": m.role, "content": m.content} for m in req.messages]
    content = await llm_client.chat(messages)
    return ChatResponse(content=content)
