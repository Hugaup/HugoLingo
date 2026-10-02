"""Shared test fixtures.

Tests run against a real PostgreSQL database (the app relies on Postgres enums
and dialect features), but a *separate* one: TEST_DATABASE_URL, default
`language_learning_test`. It is created if missing, its schema is rebuilt from
the ORM models once per run, and every table is truncated before each test.
"""
import asyncio
import os
from contextlib import AsyncExitStack

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import make_url, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://localhost/language_learning_test"
)
if "test" not in (make_url(TEST_DATABASE_URL).database or ""):
    raise RuntimeError(f"Refusing to run tests against a non-test database: {TEST_DATABASE_URL}")

# Safety net: anything that bypasses the get_db override still lands in the test DB
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

from app.database import Base, get_db  # noqa: E402
from app import models  # noqa: E402,F401 — registers ORM models
from app.main import app  # noqa: E402

# NullPool: no connection outlives a test, so nothing leaks across event loops
engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
TestSession = async_sessionmaker(engine, expire_on_commit=False)


async def _create_database_if_missing() -> None:
    url = make_url(TEST_DATABASE_URL)
    admin = create_async_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT", poolclass=NullPool)
    async with admin.connect() as conn:
        exists = await conn.scalar(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": url.database})
        if not exists:
            await conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    await admin.dispose()


async def _rebuild_schema() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)


@pytest.fixture(scope="session", autouse=True)
def _test_database():
    asyncio.run(_create_database_if_missing())
    asyncio.run(_rebuild_schema())


@pytest.fixture(autouse=True)
async def _clean_tables():
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


async def _override_get_db():
    async with TestSession() as session:
        yield session


app.dependency_overrides[get_db] = _override_get_db


@pytest.fixture
async def db():
    async with TestSession() as session:
        yield session


PERSONS = ["1s", "2s", "3s", "1p", "2p", "3p"]

# A tiny slice of the real Spanish seed data, spelled exactly as mlconjug3 stores it
SPANISH_VERBS = {
    ("tener", "Indicativo", "Indicativo presente"): ["tengo", "tienes", "tiene", "tenemos", "tenéis", "tienen"],
    ("tener", "Indicativo", "Indicativo pretérito perfecto simple"): ["tuve", "tuviste", "tuvo", "tuvimos", "tuvisteis", "tuvieron"],
    ("tener", "Indicativo", "Indicativo pretérito perfecto compuesto"): ["tenido"] * 6,
    ("tener", "Indicativo", "Indicativo pretérito imperfecto"): ["tenía", "tenías", "tenía", "teníamos", "teníais", "tenían"],
    ("ir", "Indicativo", "Indicativo pretérito perfecto simple"): ["fui", "fuiste", "fue", "fuimos", "fuisteis", "fueron"],
    ("comer", "Indicativo", "Indicativo presente"): ["como", "comes", "come", "comemos", "coméis", "comen"],
    ("comer", "Indicativo", "Indicativo pretérito perfecto simple"): ["comí", "comiste", "comió", "comimos", "comisteis", "comieron"],
    ("tener", "Subjuntivo", "Subjuntivo pretérito imperfecto (1)"): ["tuviera", "tuvieras", "tuviera", "tuviéramos", "tuvierais", "tuvieran"],
    ("tener", "Subjuntivo", "Subjuntivo pretérito imperfecto (2)"): ["tuviese", "tuvieses", "tuviese", "tuviésemos", "tuvieseis", "tuviesen"],
    ("haber", "Indicativo", "Indicativo presente"): ["he", "has", "ha", "hemos", "habéis", "han"],
    ("hablar", "Indicativo", "Indicativo presente"): ["hablo", "hablas", "habla", "hablamos", "habláis", "hablan"],
    ("hablar", "Indicativo", "Indicativo pretérito perfecto simple"): ["hablé", "hablaste", "habló", "hablamos", "hablasteis", "hablaron"],
}


@pytest.fixture
async def spanish_verbs(db):
    """Seed verb_conjugations with SPANISH_VERBS."""
    db.add_all(
        models.VerbConjugation(
            language=models.Language.spanish, verb_infinitive=verb, mood=mood, tense=tense,
            person=person, form=form,
        )
        for (verb, mood, tense), forms in SPANISH_VERBS.items()
        for person, form in zip(PERSONS, forms)
    )
    await db.commit()


@pytest.fixture
async def new_client():
    """Factory for independent clients — each one is a separate browser/cookie jar."""
    async with AsyncExitStack() as stack:
        async def _make() -> AsyncClient:
            return await stack.enter_async_context(
                AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")
            )
        yield _make


@pytest.fixture
async def client(new_client):
    return await new_client()


@pytest.fixture
async def logged_in(new_client):
    """Factory: sign up a user on a fresh client and return (client, user_json)."""
    async def _make(username: str = "alice", password: str = "pass1234"):
        c = await new_client()
        r = await c.post("/auth/signup", json={"username": username, "password": password})
        assert r.status_code == 201, r.text
        return c, r.json()
    return _make
