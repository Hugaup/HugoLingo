import importlib.util
from pathlib import Path

import pytest

from app.models import User
from tests.conftest import TestSession

SCRIPT = Path(__file__).parent.parent / "scripts" / "set_password.py"


@pytest.fixture
def script(monkeypatch):
    spec = importlib.util.spec_from_file_location("set_password", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "AsyncSessionLocal", TestSession)
    return module


async def test_claim_legacy_user_keeps_its_id(script, db, client):
    db.add(User(username="default"))
    await db.commit()

    assert await script.main("default", "mypass", rename="hugo") == 0

    r = await client.post("/auth/login", json={"username": "hugo", "password": "mypass"})
    assert r.status_code == 200
    assert r.json()["id"] == 1  # same row → existing progress history is kept


async def test_rejects_unknown_user_taken_name_and_short_password(script, db):
    db.add_all([User(username="default"), User(username="bob")])
    await db.commit()

    assert await script.main("nobody", "mypass", rename=None) == 1
    assert await script.main("default", "mypass", rename="BOB") == 1
    assert await script.main("default", "abc", rename=None) == 1


async def test_reset_logs_out_existing_sessions(script, logged_in):
    alice, _ = await logged_in("alice", "oldpass")
    assert await script.main("alice", "newpass", rename=None) == 0
    assert (await alice.get("/auth/me")).status_code == 401
