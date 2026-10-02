from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, update

from app.models import User, UserSession
from app.services.auth import SESSION_COOKIE


# ── Sign up ──────────────────────────────────────────────────────────────────

async def test_signup_logs_in_and_returns_profile(client):
    r = await client.post("/auth/signup", json={"username": "Alice", "password": "pass1234"})
    assert r.status_code == 201
    assert r.json() == {
        "id": 1, "username": "Alice", "native_language": "english",
        "target_language": None, "level": 2, "daily_goal": 20,
    }
    set_cookie = r.headers["set-cookie"].lower()
    assert SESSION_COOKIE in set_cookie and "httponly" in set_cookie and "samesite=lax" in set_cookie

    me = await client.get("/auth/me")
    assert me.status_code == 200
    assert me.json()["username"] == "Alice"


async def test_signup_stores_only_a_hash(client, db):
    await client.post("/auth/signup", json={"username": "alice", "password": "pass1234"})
    user = (await db.execute(select(User))).scalar_one()
    assert user.password_hash.startswith("scrypt$")
    assert "pass1234" not in user.password_hash


async def test_signup_rejects_taken_username_case_insensitively(client, logged_in):
    await logged_in("Alice")
    r = await client.post("/auth/signup", json={"username": "alice", "password": "pass1234"})
    assert r.status_code == 409


@pytest.mark.parametrize("username,password", [
    ("ab", "pass1234"),            # username too short
    ("has space", "pass1234"),     # invalid characters
    ("x" * 33, "pass1234"),        # username too long
    ("alice", "abc"),              # password below the 4-char minimum
])
async def test_signup_validation(client, username, password):
    r = await client.post("/auth/signup", json={"username": username, "password": password})
    assert r.status_code == 422


async def test_simple_passwords_are_allowed(client):
    # Product decision: no complexity rules, just a minimum length
    r = await client.post("/auth/signup", json={"username": "alice", "password": "abcd"})
    assert r.status_code == 201


# ── Log in / out ─────────────────────────────────────────────────────────────

async def test_login_is_case_insensitive_on_username(logged_in, client):
    await logged_in("Alice", "pass1234")
    r = await client.post("/auth/login", json={"username": "aLiCe", "password": "pass1234"})
    assert r.status_code == 200
    assert (await client.get("/auth/me")).json()["username"] == "Alice"


async def test_wrong_password_and_unknown_user_give_same_error(logged_in, client):
    await logged_in("alice", "pass1234")
    wrong_pw = await client.post("/auth/login", json={"username": "alice", "password": "nope"})
    unknown = await client.post("/auth/login", json={"username": "bob", "password": "nope"})
    assert wrong_pw.status_code == unknown.status_code == 401
    assert wrong_pw.json() == unknown.json()
    assert (await client.get("/auth/me")).status_code == 401


async def test_legacy_user_without_password_cannot_log_in(client, db):
    db.add(User(username="default"))
    await db.commit()
    r = await client.post("/auth/login", json={"username": "default", "password": ""})
    assert r.status_code == 401


async def test_logout_revokes_the_session_server_side(logged_in, new_client):
    alice, _ = await logged_in()
    token = alice.cookies[SESSION_COOKIE]

    assert (await alice.post("/auth/logout")).status_code == 204
    assert (await alice.get("/auth/me")).status_code == 401

    # Replaying the old cookie must not work either
    replay = await new_client()
    replay.cookies.set(SESSION_COOKIE, token)
    assert (await replay.get("/auth/me")).status_code == 401


async def test_logout_without_session_is_harmless(client):
    assert (await client.post("/auth/logout")).status_code == 204


async def test_multiple_devices_have_independent_sessions(logged_in, new_client):
    laptop, _ = await logged_in("alice", "pass1234")
    phone = await new_client()
    await phone.post("/auth/login", json={"username": "alice", "password": "pass1234"})

    await phone.post("/auth/logout")
    assert (await phone.get("/auth/me")).status_code == 401
    assert (await laptop.get("/auth/me")).status_code == 200


async def test_expired_session_is_rejected(logged_in, db):
    alice, _ = await logged_in()
    await db.execute(update(UserSession).values(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)))
    await db.commit()
    assert (await alice.get("/auth/me")).status_code == 401


async def test_garbage_cookie_is_rejected(client):
    client.cookies.set(SESSION_COOKIE, "not-a-real-token")
    assert (await client.get("/auth/me")).status_code == 401


# ── Protected routes ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("method,path,body", [
    ("GET", "/progress", None),
    ("GET", "/verbs/tenses/spanish", None),
    ("GET", "/verbs/search/spanish?q=ten", None),
    ("POST", "/chat", {"messages": []}),
    ("POST", "/exercises/generate", {"type": "grammar", "language": "spanish"}),
    ("POST", "/exercises/check", {"exercise_id": 1, "user_answer": "x"}),
    ("POST", "/conjugation-exercises/sentence/generate", {"language": "spanish"}),
])
async def test_app_routes_require_login(client, method, path, body):
    r = await client.request(method, path, json=body)
    assert r.status_code == 401


async def test_health_stays_public(client):
    assert (await client.get("/health")).status_code == 200


async def test_old_unauthenticated_user_endpoints_are_gone(client):
    assert (await client.post("/users", json={"username": "x"})).status_code in (404, 405)
    assert (await client.get("/users/1")).status_code == 404


# ── Settings ─────────────────────────────────────────────────────────────────

async def test_update_settings(logged_in):
    alice, _ = await logged_in()
    r = await alice.patch("/auth/me", json={"target_language": "spanish", "level": 4, "daily_goal": 30})
    assert r.status_code == 200
    me = (await alice.get("/auth/me")).json()
    assert (me["target_language"], me["level"], me["daily_goal"]) == ("spanish", 4, 30)

    # Partial update leaves other fields alone; target_language can be cleared
    me = (await alice.patch("/auth/me", json={"target_language": None})).json()
    assert (me["target_language"], me["level"], me["daily_goal"]) == (None, 4, 30)


@pytest.mark.parametrize("body", [
    {"level": 0}, {"level": 6}, {"daily_goal": 0}, {"target_language": "klingon"},
])
async def test_update_settings_validation(logged_in, body):
    alice, _ = await logged_in()
    assert (await alice.patch("/auth/me", json=body)).status_code == 422


async def test_settings_are_per_user(logged_in):
    alice, _ = await logged_in("alice")
    bob, _ = await logged_in("bob")
    await alice.patch("/auth/me", json={"level": 5})
    assert (await bob.get("/auth/me")).json()["level"] == 2


# ── Password change ──────────────────────────────────────────────────────────

async def test_change_password(logged_in, new_client):
    alice, _ = await logged_in("alice", "oldpass")
    other_device = await new_client()
    await other_device.post("/auth/login", json={"username": "alice", "password": "oldpass"})

    bad = await alice.post("/auth/password", json={"current_password": "wrong", "new_password": "newpass"})
    assert bad.status_code == 400

    ok = await alice.post("/auth/password", json={"current_password": "oldpass", "new_password": "newpass"})
    assert ok.status_code == 204

    # This device stays logged in; every other device is logged out
    assert (await alice.get("/auth/me")).status_code == 200
    assert (await other_device.get("/auth/me")).status_code == 401

    fresh = await new_client()
    assert (await fresh.post("/auth/login", json={"username": "alice", "password": "oldpass"})).status_code == 401
    assert (await fresh.post("/auth/login", json={"username": "alice", "password": "newpass"})).status_code == 200


async def test_change_password_requires_login(client):
    r = await client.post("/auth/password", json={"current_password": "a", "new_password": "bbbb"})
    assert r.status_code == 401
