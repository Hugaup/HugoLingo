from datetime import datetime, timezone

from fastapi import Cookie, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import User, UserSession
from app.services.auth import SESSION_COOKIE, hash_token


async def get_current_user(
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Resolve the session cookie to a User, or 401."""
    if not session_token:
        raise HTTPException(status_code=401, detail="Not logged in")

    result = await db.execute(
        select(User)
        .join(UserSession, UserSession.user_id == User.id)
        .where(
            UserSession.token_hash == hash_token(session_token),
            UserSession.expires_at > datetime.now(timezone.utc),
        )
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=401, detail="Session expired, please log in again")
    return user
