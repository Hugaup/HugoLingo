from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.dependencies import get_current_user
from app.routers import auth, exercises, progress, verbs, chat, conjugation_exercises, history

app = FastAPI(title="HugoLingo API")

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


@app.get("/health")
async def health():
    return {"status": "ok"}
