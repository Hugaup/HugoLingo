from datetime import datetime, timezone

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models import User, UserSession
from app.schemas import LoginRequest, PasswordChangeRequest, SignupRequest, UserResponse, UserSettingsUpdate
from app.services.auth import (
    SESSION_COOKIE,
    SESSION_LIFETIME,
    hash_password,
    hash_token,
    new_session_token,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])

BAD_CREDENTIALS = "Wrong username or password"


async def _find_user(db: AsyncSession, username: str) -> User | None:
    # Usernames keep the case they were created with but are matched case-insensitively
    result = await db.execute(select(User).where(func.lower(User.username) == username.strip().lower()))
    return result.scalar_one_or_none()


async def _start_session(db: AsyncSession, user: User, response: Response) -> None:
    now = datetime.now(timezone.utc)
    # Opportunistic cleanup so expired rows don't pile up
    await db.execute(
        delete(UserSession).where(UserSession.user_id == user.id, UserSession.expires_at <= now)
    )
    token = new_session_token()
    db.add(UserSession(user_id=user.id, token_hash=hash_token(token), expires_at=now + SESSION_LIFETIME))
    await db.commit()
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=int(SESSION_LIFETIME.total_seconds()),
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )


@router.post("/signup", response_model=UserResponse, status_code=201)
async def signup(req: SignupRequest, response: Response, db: AsyncSession = Depends(get_db)):
    if await _find_user(db, req.username):
        raise HTTPException(status_code=409, detail="That username is already taken")

    user = User(username=req.username, password_hash=await run_in_threadpool(hash_password, req.password))
    db.add(user)
    await db.flush()
    await _start_session(db, user, response)
    await db.refresh(user)
    return user


@router.post("/login", response_model=UserResponse)
async def login(req: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
    user = await _find_user(db, req.username)
    if user is None or not await run_in_threadpool(verify_password, req.password, user.password_hash):
        raise HTTPException(status_code=401, detail=BAD_CREDENTIALS)

    await _start_session(db, user, response)
    return user


@router.post("/logout", status_code=204)
async def logout(
    response: Response,
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    db: AsyncSession = Depends(get_db),
):
    if session_token:
        await db.execute(delete(UserSession).where(UserSession.token_hash == hash_token(session_token)))
        await db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")


@router.get("/me", response_model=UserResponse)
async def me(user: User = Depends(get_current_user)):
    return user


@router.patch("/me", response_model=UserResponse)
async def update_me(
    req: UserSettingsUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    for field, value in req.model_dump(exclude_unset=True).items():
        if value is None and field != "target_language":
            continue  # only target_language may be cleared
        setattr(user, field, value)
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/password", status_code=204)
async def change_password(
    req: PasswordChangeRequest,
    session_token: str = Cookie(alias=SESSION_COOKIE),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not await run_in_threadpool(verify_password, req.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    user.password_hash = await run_in_threadpool(hash_password, req.new_password)
    # Log out every other device; keep the session that made the change
    await db.execute(
        delete(UserSession).where(
            UserSession.user_id == user.id,
            UserSession.token_hash != hash_token(session_token),
        )
    )
    await db.commit()
