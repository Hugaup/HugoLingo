from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import select

from app.models import Attempt, Exercise, ExerciseType, Language, ReviewItem
from app.services import history, llm

PRETERITO = {"mood": "Indicativo", "tense": "Indicativo pretérito perfecto simple"}
PRESENTE = {"mood": "Indicativo", "tense": "Indicativo presente"}


def drill(verb, person, answer, tense=PRETERITO):
    return {"language": "spanish", "verb_infinitive": verb, "person": person, "answer": answer, **tense}


async def reviews(db):
    return {(r.verb_infinitive, r.tense): r for r in (await db.execute(select(ReviewItem))).scalars()}


# ── Drill grading (server-side, against verb_conjugations) ───────────────────

async def test_drill_check_grades_and_records(logged_in, spanish_verbs, db):
    alice, user = await logged_in()

    r = await alice.post("/history/drill/check", json=drill("tener", "1s", "tuve"))
    assert r.json() == {"is_correct": True, "result": "correct", "expected": "tuve", "alternates": [], "explanation": None}

    r = await alice.post("/history/drill/check", json=drill("tener", "3s", "tenió"))
    assert r.json()["is_correct"] is False
    assert r.json()["expected"] == "tuvo"

    rows = (await db.execute(select(Attempt).order_by(Attempt.id))).scalars().all()
    assert [(a.user_id, a.source, a.person, a.user_answer, a.is_correct) for a in rows] == [
        (user["id"], "drill", "1s", "tuve", True),
        (user["id"], "drill", "3s", "tenió", False),
    ]


async def test_drill_check_ignores_case_and_extra_spaces(logged_in, spanish_verbs):
    alice, _ = await logged_in()
    r = await alice.post("/history/drill/check", json=drill("tener", "1s", "  TUVE "))
    assert r.json()["is_correct"] is True


async def test_drill_check_builds_compound_tenses(logged_in, spanish_verbs):
    alice, _ = await logged_in()
    compuesto = {"mood": "Indicativo", "tense": "Indicativo pretérito perfecto compuesto"}
    r = await alice.post("/history/drill/check", json=drill("tener", "1s", "he tenido", compuesto))
    assert (r.json()["result"], r.json()["expected"], r.json()["alternates"]) == ("correct", "he tenido", [])
    r = await alice.post("/history/drill/check", json=drill("tener", "1s", "tenido", compuesto))
    assert r.json()["is_correct"] is False


async def test_drill_check_accepts_both_subjunctive_spellings(logged_in, spanish_verbs, db):
    alice, _ = await logged_in()
    subj = {"mood": "Subjuntivo", "tense": "Subjuntivo pretérito imperfecto"}  # canonical name
    r = await alice.post("/history/drill/check", json=drill("tener", "1s", "tuviese", subj))
    assert (r.json()["result"], r.json()["expected"], r.json()["alternates"]) == ("correct", "tuviera", ["tuviese"])
    # Both spellings are one tense in the history
    assert (await db.execute(select(Attempt.tense))).scalar_one() == "Subjuntivo pretérito imperfecto"


async def test_drill_check_unknown_prompt(logged_in, spanish_verbs):
    alice, _ = await logged_in()
    r = await alice.post("/history/drill/check", json=drill("volar", "1s", "volé"))
    assert r.status_code == 404


# ── Spaced review boxes ──────────────────────────────────────────────────────

async def test_review_box_moves_up_on_right_and_resets_on_wrong(logged_in, spanish_verbs, db):
    alice, _ = await logged_in()
    await alice.post("/history/drill/check", json=drill("tener", "1s", "tuve"))
    await alice.post("/history/drill/check", json=drill("tener", "2s", "tuviste"))
    item = (await reviews(db))[("tener", PRETERITO["tense"])]
    assert (item.box, item.correct_count, item.wrong_count) == (2, 2, 0)
    assert item.due_at > datetime.now(timezone.utc) + timedelta(days=2)

    await alice.post("/history/drill/check", json=drill("tener", "3s", "tenió"))
    await db.refresh(item)
    assert (item.box, item.wrong_count) == (0, 1)
    assert item.due_at <= datetime.now(timezone.utc)


async def test_verb_table_batch_moves_each_box_once(logged_in, db):
    alice, user = await logged_in()
    cells = [
        {"verb_infinitive": "tener", **PRESENTE, "person": p, "user_answer": f, "expected": f, "is_correct": True}
        for p, f in [("1s", "tengo"), ("2s", "tienes"), ("3s", "tiene")]
    ] + [
        {"verb_infinitive": "hablar", **PRESENTE, "person": "1s", "user_answer": "hablo", "expected": "hablo", "is_correct": True},
        {"verb_infinitive": "hablar", **PRESENTE, "person": "2s", "user_answer": "hablo", "expected": "hablas", "is_correct": False},
    ]
    r = await alice.post("/history/attempts", json={"language": "spanish", "source": "verb_table", "attempts": cells})
    assert r.status_code == 204

    rows = (await db.execute(select(Attempt))).scalars().all()
    assert len(rows) == 5 and all(a.source == "verb_table" and a.user_id == user["id"] for a in rows)
    items = await reviews(db)
    assert items[("tener", PRESENTE["tense"])].box == 1      # all right → up once, not three times
    assert items[("hablar", PRESENTE["tense"])].box == 0     # one wrong → back to 0


@pytest.mark.parametrize("body", [
    {"language": "spanish", "source": "drill", "attempts": []},     # server-graded sources can't self-report
    {"language": "spanish", "source": "verb_table", "attempts": [
        {"verb_infinitive": "x", "user_answer": "a", "expected": "b", "is_correct": True}] * 301},
])
async def test_record_attempts_validation(logged_in, body):
    alice, _ = await logged_in()
    assert (await alice.post("/history/attempts", json=body)).status_code == 422


# ── Weak spots ("Work on this") ──────────────────────────────────────────────

async def test_weak_spots_point_at_the_verb_and_tense_you_struggle_with(logged_in, spanish_verbs):
    alice, _ = await logged_in()
    for person, wrong in [("1s", "tení"), ("3s", "tenió"), ("1p", "tenimos")]:
        await alice.post("/history/drill/check", json=drill("tener", person, wrong))
    for person, right in [("1s", "hablé"), ("2s", "hablaste"), ("3s", "habló")]:
        await alice.post("/history/drill/check", json=drill("hablar", person, right))
    await alice.post("/history/drill/check", json=drill("tener", "1s", "tengo", PRESENTE))

    data = (await alice.get("/history/weak-spots/spanish")).json()
    assert [v["verb_infinitive"] for v in data["verbs"]] == ["tener"]
    assert data["verbs"][0]["mistakes"] == 3 and data["verbs"][0]["attempts"] == 4
    assert [(c["verb_infinitive"], c["tense"]) for c in data["combos"]] == [("tener", PRETERITO["tense"])]
    assert [t["tense"] for t in data["tenses"]] == [PRETERITO["tense"]]
    assert data["due_count"] == 1


async def test_weak_spots_are_per_user_and_per_language(logged_in, spanish_verbs):
    alice, _ = await logged_in("alice")
    bob, _ = await logged_in("bob")
    await alice.post("/history/drill/check", json=drill("tener", "1s", "tení"))

    assert (await bob.get("/history/weak-spots/spanish")).json()["verbs"] == []
    assert (await alice.get("/history/weak-spots/french")).json()["verbs"] == []
    assert len((await alice.get("/history/weak-spots/spanish")).json()["verbs"]) == 1


async def test_new_user_has_no_weak_spots(logged_in):
    alice, _ = await logged_in()
    data = (await alice.get("/history/weak-spots/spanish")).json()
    assert data == {"verbs": [], "tenses": [], "combos": [], "due_count": 0}


# ── Drill prompts ────────────────────────────────────────────────────────────

async def test_drill_targets_weak_items_and_missed_persons_first(logged_in, spanish_verbs):
    alice, _ = await logged_in()
    await alice.post("/history/drill/check", json=drill("tener", "3s", "tenió"))
    await alice.post("/history/drill/check", json=drill("hablar", "1s", "hablé"))

    prompts = (await alice.get("/history/drill/spanish?count=4")).json()
    assert len(prompts) == 4
    # Only tener is due/weak; hablar was answered right so it isn't drilled
    assert {p["verb_infinitive"] for p in prompts} == {"tener"}
    assert prompts[0]["person"] == "3s"  # the person that was missed comes first
    assert prompts[0]["reason"] == "due"
    assert len({p["person"] for p in prompts}) == 4  # no repeated prompts


async def test_drill_is_empty_without_history(logged_in, spanish_verbs):
    alice, _ = await logged_in()
    assert (await alice.get("/history/drill/spanish")).json() == []


# ── Recording from the other practice areas ──────────────────────────────────

SENTENCE_ITEM = {
    "sentence": "Ayer yo ___ mucho trabajo.", "subject_hint": "yo", "verb_infinitive": "tener",
    "mood": "Indicativo", "tense": "Indicativo pretérito perfecto simple", "person": "1s",
    "correct_form": "tuve", "alternates": [],
}


@pytest.fixture
def fake_llm(monkeypatch):
    async def chat(messages, **kwargs):
        return "Because it's a completed action in the past."
    monkeypatch.setattr(llm.llm_client, "chat", chat)


async def test_sentence_check_records_the_answer(logged_in, fake_llm, db):
    alice, user = await logged_in()
    r = await alice.post("/conjugation-exercises/sentence/check", json={
        "item": SENTENCE_ITEM, "user_form": "tuve", "language": "spanish",
        "user_mood": "Indicativo", "user_tense": "Indicativo pretérito imperfecto",
    })
    assert r.status_code == 200
    assert (r.json()["form_correct"], r.json()["tense_correct"]) == (True, False)

    a = (await db.execute(select(Attempt))).scalar_one()
    assert (a.user_id, a.source, a.verb_infinitive, a.tense, a.person) == (
        user["id"], "sentence", "tener", SENTENCE_ITEM["tense"], "1s",
    )
    assert a.is_correct is False  # right form but wrong tense named still counts as a miss


async def test_sentence_check_never_waits_on_the_llm(logged_in, monkeypatch, db):
    # The check used to block ~10 s on an LLM explanation; now it must not call the LLM at all,
    # so it's instant and still works with Ollama down
    async def broken(messages, **kwargs):
        raise httpx.ConnectError("ollama down")
    monkeypatch.setattr(llm.llm_client, "chat", broken)

    alice, _ = await logged_in()
    r = await alice.post("/conjugation-exercises/sentence/check", json={
        "item": SENTENCE_ITEM, "user_form": "tuve", "language": "spanish",
        "user_mood": "Indicativo", "user_tense": "Indicativo pretérito perfecto simple",
    })
    assert r.status_code == 200
    assert (await db.execute(select(Attempt.is_correct))).scalar_one() is True


async def test_old_conjugation_exercise_counts_toward_verb_history(logged_in, db):
    alice, _ = await logged_in()
    exercise = Exercise(type=ExerciseType.conjugation, language=Language.spanish, difficulty=2, content={
        "sentence": "Ayer ___ frío.", "verb_infinitive": "Tener", "correct_answer": "tuve",
        "tense": "simple past", "subject": "yo", "explanation": "...",
    })
    db.add(exercise)
    await db.commit()

    await alice.post("/exercises/check", json={"exercise_id": exercise.id, "user_answer": "tenía"})

    a = (await db.execute(select(Attempt))).scalar_one()
    assert (a.source, a.verb_infinitive, a.mood, a.tense, a.is_correct) == ("exercise", "tener", None, None, False)
    data = (await alice.get("/history/weak-spots/spanish")).json()
    assert [v["verb_infinitive"] for v in data["verbs"]] == ["tener"]
    assert data["combos"] == []  # no DB tense to attribute it to
    assert (await db.execute(select(ReviewItem))).first() is None


# ── Stats and grid ───────────────────────────────────────────────────────────

def _attempt(user_id, created_at, is_correct=True):
    return Attempt(user_id=user_id, language=Language.spanish, source="drill", verb_infinitive="tener",
                   mood=PRETERITO["mood"], tense=PRETERITO["tense"], person="1s",
                   user_answer="x", expected="tuve", is_correct=is_correct, created_at=created_at)


async def test_stats_totals_streak_and_daily_activity(logged_in, db):
    alice, user = await logged_in()
    now = datetime.now(timezone.utc)
    db.add_all(_attempt(user["id"], now - age, ok) for age, ok in [
        (timedelta(0), True), (timedelta(0), False),
        (timedelta(days=1), True),
        (timedelta(days=2), True),
        (timedelta(days=5), False),
    ])
    await db.commit()

    data = (await alice.get("/history/stats?language=spanish&days=7")).json()
    assert (data["total"], data["correct"], data["accuracy"]) == (5, 3, 60.0)
    assert data["today_count"] == 2
    assert data["streak_days"] == 3
    assert [d["total"] for d in data["daily"]] == [0, 1, 0, 0, 1, 1, 2]
    assert (data["daily"][-1]["total"], data["daily"][-1]["correct"]) == (2, 1)


async def test_stats_days_follow_the_users_timezone(logged_in, db):
    _, user = await logged_in()
    now = datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc)
    # 23:30 UTC on Oct 1 is already 08:30 on Oct 2 in Tokyo
    db.add(_attempt(user["id"], datetime(2026, 10, 1, 23, 30, tzinfo=timezone.utc)))
    await db.commit()

    utc = await history.stats(db, user["id"], None, "UTC", 2, now)
    tokyo = await history.stats(db, user["id"], None, "Asia/Tokyo", 2, now)
    assert (utc["today_count"], [d["total"] for d in utc["daily"]]) == (0, [1, 0])
    assert (tokyo["today_count"], [d["total"] for d in tokyo["daily"]]) == (1, [0, 1])


async def test_stats_for_a_new_user(logged_in):
    alice, _ = await logged_in()
    data = (await alice.get("/history/stats")).json()
    assert (data["total"], data["accuracy"], data["streak_days"], data["today_count"]) == (0, 0.0, 0, 0)
    assert len(data["daily"]) == 30


async def test_grid_shows_accuracy_per_verb_and_tense(logged_in, spanish_verbs):
    alice, _ = await logged_in()
    await alice.post("/history/drill/check", json=drill("tener", "1s", "tuve"))
    await alice.post("/history/drill/check", json=drill("tener", "2s", "tuvo"))
    await alice.post("/history/drill/check", json=drill("tener", "1s", "tengo", PRESENTE))
    await alice.post("/history/drill/check", json=drill("hablar", "1s", "hablo", PRESENTE))

    data = (await alice.get("/history/grid/spanish")).json()
    assert [r["verb_infinitive"] for r in data["rows"]] == ["tener", "hablar"]  # most practised first
    assert {(t["mood"], t["tense"]) for t in data["tenses"]} == {
        (PRESENTE["mood"], PRESENTE["tense"]), (PRETERITO["mood"], PRETERITO["tense"]),
    }
    tener = data["rows"][0]["cells"]
    assert tener[f"Indicativo||{PRETERITO['tense']}"] == {"attempts": 2, "correct": 1}
    assert tener[f"Indicativo||{PRESENTE['tense']}"] == {"attempts": 1, "correct": 1}


@pytest.mark.parametrize("method,path", [
    ("GET", "/history/weak-spots/spanish"),
    ("GET", "/history/drill/spanish"),
    ("POST", "/history/drill/check"),
    ("POST", "/history/attempts"),
    ("GET", "/history/stats"),
    ("GET", "/history/grid/spanish"),
])
async def test_history_requires_login(client, method, path):
    assert (await client.request(method, path, json={})).status_code == 401
