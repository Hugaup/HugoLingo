"""Password hashing and session tokens — pure functions, no DB or FastAPI.

Passwords are hashed with stdlib scrypt (no extra dependency). Stored format:
    scrypt$<n>$<r>$<p>$<salt hex>$<hash hex>
so the cost parameters can be raised later without breaking existing hashes.

Session tokens are random strings handed to the browser in a cookie; only their
SHA-256 is stored in `user_sessions`, so a DB leak doesn't leak live sessions.
"""
import hashlib
import hmac
import secrets
from datetime import timedelta

SESSION_COOKIE = "hugolingo_session"
SESSION_LIFETIME = timedelta(days=30)

_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P)
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        scheme, n, r, p, salt_hex, digest_hex = stored.split("$")
        if scheme != "scrypt":
            return False
        digest = hashlib.scrypt(
            password.encode(), salt=bytes.fromhex(salt_hex), n=int(n), r=int(r), p=int(p)
        )
    except ValueError:
        return False
    return hmac.compare_digest(digest.hex(), digest_hex)


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
