from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import exercises, progress, verbs, chat, conjugation_exercises

app = FastAPI(title="HugoLingo API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(exercises.router)
app.include_router(progress.router)
app.include_router(verbs.router)
app.include_router(chat.router)
app.include_router(conjugation_exercises.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
