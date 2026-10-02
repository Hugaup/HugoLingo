import random
import re

import pytest
from sqlalchemy import func, select

from app.models import Language, SentencePoolItem
from app.routers import conjugation_exercises
from app.schemas import TenseFilter
from app.services import sentence_pool
from tests.conftest import TestSession

PRESENTE = {"mood": "Indicativo", "tense": "Indicativo presente"}
SUBJ = {"mood": "Subjuntivo", "tense": "Subjuntivo pretérito imperfecto"}


def pool_row(**overrides):
    values = dict(
        language=Language.spanish, verb_infinitive="tener", **PRESENTE, person="1s",
        sentence="Todos los días yo ___ hambre.", subject_hint="yo", correct_form="tengo",
        alternates=[], model="test-model",
    )
    return SentencePoolItem(**(values | overrides))


async def count_pool(db):
    return await db.scalar(select(func.count()).select_from(SentencePoolItem))


class FakeLLM:
    """Writes a valid sentence for whatever subject the real prompt asks for."""
    model = "fake-llm"

    def __init__(self, fail=False):
        self.fail = fail
        self.calls = 0

    async def chat_json(self, messages, max_tokens=None):
        self.calls += 1
        if self.fail:
            return {"sentence": "no blank here", "subject_hint": "yo"}
        pronoun = re.search(r"subject MUST be '([^']+)'", messages[1]["content"]).group(1)
        return {"sentence": f"Todos los días {pronoun} ___ en casa.", "subject_hint": pronoun}


# ── Serving from the stock ───────────────────────────────────────────────────

async def test_take_serves_matching_sentences_and_removes_them(db):
    db.add_all([pool_row(), pool_row(person="2s"), pool_row(**SUBJ, correct_form="tuviera")])
    await db.commit()

    items = await sentence_pool.take(db, Language.spanish, [TenseFilter(**PRESENTE)], 5)
    assert {i.person for i in items} == {"1s", "2s"}
    assert all(i.tense == PRESENTE["tense"] for i in items)
    assert await count_pool(db) == 1  # served sentences are never shown again


async def test_take_matches_either_subjunctive_spelling_and_respects_count(db):
    db.add_all([pool_row(**SUBJ, person=p, correct_form="tuviera") for p in ["1s", "2s", "3s"]])
    await db.commit()
    asked = [TenseFilter(mood="Subjuntivo", tense="Subjuntivo pretérito imperfecto (1)")]
    assert len(await sentence_pool.take(db, Language.spanish, asked, 2)) == 2
    assert await count_pool(db) == 1


async def test_take_from_an_empty_or_other_language_stock(db):
    db.add(pool_row(language=Language.french))
    await db.commit()
    assert await sentence_pool.take(db, Language.spanish, [], 3) == []


async def test_generate_endpoint_answers_from_the_stock_without_the_llm(logged_in, db, monkeypatch):
    db.add_all([pool_row(person=p) for p in ["1s", "2s", "3s"]])
    await db.commit()

    async def no_llm(*args, **kwargs):
        raise AssertionError("should not call the LLM when the stock has enough")
    monkeypatch.setattr(conjugation_exercises, "generate_one", no_llm)

    alice, _ = await logged_in()
    r = await alice.post("/conjugation-exercises/sentence/generate",
                         json={"language": "spanish", "tenses": [PRESENTE], "count": 3})
    assert r.status_code == 200
    assert len(r.json()) == 3 and await count_pool(db) == 0


async def test_generate_endpoint_tops_up_live_when_the_stock_runs_short(logged_in, db, spanish_verbs, monkeypatch):
    db.add(pool_row())
    await db.commit()
    fake = FakeLLM()
    real_generate = conjugation_exercises.generate_one
    monkeypatch.setattr(conjugation_exercises, "generate_one",
                        lambda db, lang, tenses: real_generate(db, lang, tenses, fake))

    alice, _ = await logged_in()
    r = await alice.post("/conjugation-exercises/sentence/generate",
                         json={"language": "spanish", "tenses": [PRESENTE], "count": 3})
    assert r.status_code == 200
    assert len(r.json()) == 3
    assert fake.calls == 2  # 1 from the stock, 2 generated live


# ── Refilling ────────────────────────────────────────────────────────────────

async def test_refill_fills_the_stock_up_to_the_target(db, spanish_verbs):
    fake = FakeLLM()
    added = await sentence_pool.refill(
        Language.spanish, target=4, session_factory=TestSession, client=fake,
        rng=random.Random(1), wait_while_busy=False,
    )
    assert added == 4 and await count_pool(db) == 4
    rows = (await db.execute(select(SentencePoolItem))).scalars().all()
    assert {r.model for r in rows} == {"fake-llm"}
    assert all("___" in r.sentence and r.correct_form not in r.sentence for r in rows)

    # Already full: nothing more to do
    assert await sentence_pool.refill(Language.spanish, target=4, session_factory=TestSession,
                                      client=fake, wait_while_busy=False) == 0


async def test_refill_gives_up_when_every_output_is_rejected(db, spanish_verbs):
    fake = FakeLLM(fail=True)
    added = await sentence_pool.refill(Language.spanish, target=5, session_factory=TestSession,
                                       client=fake, wait_while_busy=False)
    assert added == 0
    assert fake.calls == sentence_pool.MAX_FAILURES_IN_A_ROW


async def test_refill_for_a_language_without_verb_data_stops_immediately(db, spanish_verbs):
    fake = FakeLLM()
    assert await sentence_pool.refill(Language.norwegian, target=3, session_factory=TestSession,
                                      client=fake, wait_while_busy=False) == 0
    assert fake.calls == 0


def test_refill_follows_what_users_recently_asked_for(monkeypatch):
    monkeypatch.setattr(sentence_pool, "_recent_requests", {})
    rng = random.Random(0)
    everyday = sentence_pool._choose_tenses(Language.spanish, rng)
    assert len(everyday) > 1  # no requests yet → the everyday tenses

    sentence_pool._recent_requests.setdefault(Language.spanish, sentence_pool.deque(maxlen=20))
    sentence_pool.note_request(Language.spanish, [TenseFilter(**SUBJ)])
    picks = [sentence_pool._choose_tenses(Language.spanish, rng) for _ in range(50)]
    assert sum(p == [TenseFilter(**SUBJ)] for p in picks) > 25


def test_live_requests_pause_background_refills():
    assert sentence_pool._live_requests == 0
    with sentence_pool.live_request():
        assert sentence_pool._live_requests == 1
    assert sentence_pool._live_requests == 0


def test_scheduling_is_a_no_op_when_the_pool_is_disabled():
    # SENTENCE_POOL_ENABLED=false in tests: no background tasks may start
    sentence_pool.schedule_refill(Language.spanish)
    assert not sentence_pool._tasks
