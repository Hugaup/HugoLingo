#!/usr/bin/env python3
"""Set (or reset) a user's password, optionally renaming them.

Main use: claim an account created before login existed (e.g. the old
hardcoded "default" user, id 1) so its progress history isn't lost.
Run from the backend/ directory:
    source .venv/bin/activate
    python scripts/set_password.py default mypassword --rename hugo
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import delete, func, select

from app.database import AsyncSessionLocal
from app.models import User, UserSession
from app.schemas import PASSWORD_MIN_LENGTH
from app.services.auth import hash_password


async def main(username: str, password: str, rename: str | None) -> int:
    if len(password) < PASSWORD_MIN_LENGTH:
        print(f"Password must be at least {PASSWORD_MIN_LENGTH} characters.")
        return 1

    async with AsyncSessionLocal() as db:
        user = (await db.execute(
            select(User).where(func.lower(User.username) == username.lower())
        )).scalar_one_or_none()
        if user is None:
            print(f"No user named '{username}'.")
            return 1

        if rename:
            taken = (await db.execute(
                select(User).where(func.lower(User.username) == rename.lower(), User.id != user.id)
            )).scalar_one_or_none()
            if taken:
                print(f"Username '{rename}' is already taken.")
                return 1
            user.username = rename

        user.password_hash = hash_password(password)
        # A password reset logs out every existing session
        await db.execute(delete(UserSession).where(UserSession.user_id == user.id))
        await db.commit()
        print(f"Password set for user #{user.id} '{user.username}'.")
        return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("username")
    parser.add_argument("password")
    parser.add_argument("--rename", help="new username for this account")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.username, args.password, args.rename)))
