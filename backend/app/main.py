import asyncio
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.dependencies import get_current_user
from app.routers import (
    auth, chat, conjugation_exercises, conversation, exercises, grammar, history, progress, verbs, vocabulary,
)
from app.services import sentence_pool
from app.services.llm import llm_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Both run in the background: the API is usable immediately, even with Ollama down
    if settings.llm_warmup:
        warm_up = asyncio.create_task(llm_client.warm_up())
    sentence_pool.start()
    yield
    await sentence_pool.stop()
    if settings.llm_warmup:
        warm_up.cancel()


app = FastAPI(title="HugoLingo API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)

# Everything except /auth and /health requires a logged-in user
login_required = [Depends(get_current_user)]
app.include_router(exercises.router, dependencies=login_required)
app.include_router(progress.router, dependencies=login_required)
app.include_router(verbs.router, dependencies=login_required)
app.include_router(chat.router, dependencies=login_required)
app.include_router(conjugation_exercises.router, dependencies=login_required)
app.include_router(history.router, dependencies=login_required)
app.include_router(vocabulary.router, dependencies=login_required)
app.include_router(conversation.router, dependencies=login_required)
app.include_router(grammar.router, dependencies=login_required)


@app.get("/health")
async def health():
    return {"status": "ok"}
