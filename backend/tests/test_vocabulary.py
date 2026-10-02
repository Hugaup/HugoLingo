from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select

from app.models import Language, VocabAttempt, VocabItem, VocabReview
from app.services import vocabulary
from app.services.vocabulary import accepted_answers, cloze, grade_answer, level_from_rank, load_entries, upsert_items

TOPICS = {"people", "home", "food", "time", "places", "work_school", "body_health", "feelings", "nature", "describing", "verbs"}
PHRASE_TOPICS = {"greetings", "politeness", "basics", "out_and_about", "social"}


@pytest.fixture
async def vocab(db):
    """The real Spanish and French vocabulary files, loaded into the test DB."""
    for language in vocabulary.VOCAB_LANGUAGES:
        await upsert_items(db, load_entries(language))


async def item(db, text, language=Language.spanish):
    return (await db.execute(
        select(VocabItem).where(VocabItem.language == language, VocabItem.text == text)
    )).scalar_one()


# ── The data files themselves ────────────────────────────────────────────────

@pytest.mark.parametrize("language", vocabulary.VOCAB_LANGUAGES)
def test_vocabulary_file_is_complete_and_consistent(language):
    rows = load_entries(language)
    words = [r for r in rows if r["kind"] == "word"]
    phrases = [r for r in rows if r["kind"] == "phrase"]
    assert len(words) >= 250 and len(phrases) >= 40
    assert len({(r["kind"], r["text"]) for r in rows}) == len(rows), "duplicate entries"
    assert {r["topic"] for r in words} == TOPICS
    assert {r["topic"] for r in phrases} == PHRASE_TOPICS
    for r in rows:
        assert r["translation"].strip() and r["example"].strip() and r["example_translation"].strip(), r["text"]
        assert r["frequency_rank"], f"{r['text']} has no frequency rank"
    # Every word's example must contain it exactly once, or fill-the-gap can't be built
    for r in words:
        assert cloze(VocabItem(**r)) is not None, f"example for {r['text']!r} can't be blanked: {r['example']}"


def test_level_comes_from_frequency():
    assert [level_from_rank(r, "word") for r in (5, 1500, 1501, 4000, 4001, None)] == [1, 1, 2, 2, 3, 1]
    assert level_from_rank(9999, "phrase") == 1  # everyday phrases are always beginner level


async def test_seeding_is_idempotent_and_applies_edits(db, vocab):
    before = await db.scalar(select(func.count()).select_from(VocabItem))
    rows = load_entries(Language.spanish)
    casa = next(r for r in rows if r["text"] == "casa")
    casa["translation"] = "house; home; dwelling"
    await upsert_items(db, rows)
    assert await db.scalar(select(func.count()).select_from(VocabItem)) == before
    db.expire_all()
    assert (await item(db, "casa")).translation == "house; home; dwelling"


# ── Accepted answers & grading ───────────────────────────────────────────────

async def test_accepted_answers(db, vocab):
    casa, eau, comer, pescado = (await item(db, "casa"), await item(db, "eau", Language.french),
                                 await item(db, "comer"), await item(db, "pescado"))
    assert accepted_answers(casa, "type_to_target") == ["casa", "la casa"]
    assert accepted_answers(eau, "type_to_target") == ["eau", "l'eau"]
    assert accepted_answers(casa, "cloze") == ["casa"]
    assert {"house", "home"} <= set(accepted_answers(casa, "type_to_native"))
    assert {"to eat", "eat", "to have lunch", "have lunch"} <= set(accepted_answers(comer, "type_to_native"))
    assert "fish" in accepted_answers(pescado, "type_to_native")  # "fish (food)" without the note


@pytest.mark.parametrize("text,exercise,answer,result", [
    ("casa", "type_to_target", "la casa", "correct"),
    ("casa", "type_to_target", "  CASA ", "correct"),
    ("habitación", "type_to_target", "habitacion", "almost"),
    ("casa", "type_to_target", "piso", "wrong"),
    ("casa", "type_to_native", "the house", "correct"),
    ("¿qué tal?", "type_to_target", "Qué tal", "correct"),        # punctuation doesn't matter
    ("¿qué tal?", "type_to_target", "que tal", "almost"),
    ("de nada", "type_to_native", "you're welcome", "correct"),
    ("de nada", "type_to_native", "you’re welcome", "correct"),   # curly apostrophe
])
async def test_grading(db, vocab, text, exercise, answer, result):
    graded, _ = grade_answer(await item(db, text), exercise, answer)
    assert graded.result == result


# ── API ──────────────────────────────────────────────────────────────────────

async def check(client, item_id, exercise, answer="", knew=None):
    body = {"item_id": item_id, "exercise": exercise, "answer": answer}
    if knew is not None:
        body["knew"] = knew
    r = await client.post("/vocab/check", json=body)
    assert r.status_code == 200, r.text
    return r.json()


async def test_check_grades_records_and_schedules(logged_in, db, vocab):
    alice, user = await logged_in()
    casa = await item(db, "casa")

    data = await check(alice, casa.id, "type_to_target", "la casa")
    assert (data["result"], data["expected"], data["box"]) == ("correct", "casa", 1)

    hab = await item(db, "habitación")
    data = await check(alice, hab.id, "type_to_target", "habitacion")
    assert (data["result"], data["is_correct"], data["box"]) == ("almost", False, 0)

    attempts = (await db.execute(select(VocabAttempt).order_by(VocabAttempt.id))).scalars().all()
    assert [(a.user_id, a.exercise, a.is_correct, a.is_almost) for a in attempts] == [
        (user["id"], "type_to_target", True, False), (user["id"], "type_to_target", False, True),
    ]


async def test_flashcards_are_self_graded(logged_in, db, vocab):
    alice, _ = await logged_in()
    gato = await item(db, "gato")
    assert (await check(alice, gato.id, "flashcard", knew=True))["box"] == 1
    assert (await check(alice, gato.id, "flashcard", knew=False))["box"] == 0
    r = await alice.post("/vocab/check", json={"item_id": gato.id, "exercise": "flashcard"})
    assert r.status_code == 422


async def test_multiple_choice_is_never_almost(logged_in, db, vocab):
    alice, _ = await logged_in()
    hab = await item(db, "habitación")
    assert (await check(alice, hab.id, "choice_to_target", "la habitación"))["result"] == "correct"
    assert (await check(alice, hab.id, "choice_to_target", "habitacion"))["result"] == "wrong"


async def test_check_unknown_item(logged_in, vocab):
    alice, _ = await logged_in()
    r = await alice.post("/vocab/check", json={"item_id": 999999, "exercise": "cloze", "answer": "x"})
    assert r.status_code == 404


async def test_session_new_user_gets_common_words_with_options_and_gaps(logged_in, db, vocab):
    alice, _ = await logged_in()
    items = (await alice.get("/vocab/spanish/session?kind=word&topic=food&count=8")).json()
    assert len(items) == 8 and len({i["id"] for i in items}) == 8
    assert all(i["is_new"] and i["topic"] == "food" and i["level"] == 1 for i in items)
    for i in items:
        assert len(i["options"]) == 3
        assert all(o["pos"] == i["pos"] and o["text"] != i["text"] for o in i["options"])
        assert i["cloze"] and "___" in i["cloze"] and i["text"] not in i["cloze"]


async def test_session_puts_due_reviews_first(logged_in, db, vocab):
    alice, _ = await logged_in()
    gato = await item(db, "gato")
    await check(alice, gato.id, "flashcard", knew=False)  # wrong → due straight away
    items = (await alice.get("/vocab/spanish/session?kind=word&topic=nature&count=3")).json()
    assert gato.id in [i["id"] for i in items]
    assert next(i for i in items if i["id"] == gato.id)["is_new"] is False


async def test_phrases_session(logged_in, vocab):
    alice, _ = await logged_in()
    items = (await alice.get("/vocab/french/session?kind=phrase&count=5")).json()
    assert len(items) == 5 and all(i["kind"] == "phrase" for i in items)


async def test_overview_tracks_seen_learned_and_due(logged_in, db, vocab):
    alice, _ = await logged_in()
    data = (await alice.get("/vocab/spanish/overview")).json()
    assert data["available"] is True and data["learned"] == 0 and data["due"] == 0
    assert data["total"] == len(load_entries(Language.spanish))
    food = next(g for g in data["groups"] if g["kind"] == "word" and g["topic"] == "food")
    assert food["seen"] == 0

    pan = await item(db, "pan")
    for _ in range(3):
        await check(alice, pan.id, "type_to_target", "pan")
    await check(alice, (await item(db, "leche")).id, "type_to_target", "zzz")

    data = (await alice.get("/vocab/spanish/overview")).json()
    food = next(g for g in data["groups"] if g["kind"] == "word" and g["topic"] == "food")
    assert (food["seen"], food["learned"], food["due"]) == (2, 1, 1)
    assert (data["learned"], data["due"]) == (1, 1)


async def test_overview_for_a_language_without_vocabulary(logged_in, vocab):
    alice, _ = await logged_in()
    data = (await alice.get("/vocab/english/overview")).json()
    assert data == {"available": False, "groups": [], "total": 0, "learned": 0, "due": 0}


async def test_browse_items_shows_the_users_box(logged_in, db, vocab):
    alice, _ = await logged_in()
    hola = await item(db, "hola")
    await check(alice, hola.id, "type_to_target", "hola")
    rows = (await alice.get("/vocab/spanish/items?kind=phrase&topic=greetings")).json()
    assert {r["text"]: r["box"] for r in rows}["hola"] == 1
    assert all(r["kind"] == "phrase" and r["topic"] == "greetings" for r in rows)


async def test_vocabulary_answers_count_toward_daily_activity(logged_in, db, vocab):
    alice, _ = await logged_in()
    await check(alice, (await item(db, "pan")).id, "type_to_target", "pan")
    await check(alice, (await item(db, "lait", Language.french)).id, "type_to_target", "zzz")
    stats = (await alice.get("/history/stats")).json()
    assert (stats["today_count"], stats["total"], stats["streak_days"]) == (2, 2, 1)
    spanish = (await alice.get("/history/stats?language=spanish")).json()
    assert (spanish["total"], spanish["correct"]) == (1, 1)


async def test_reviews_belong_to_each_user(logged_in, db, vocab):
    alice, _ = await logged_in("alice")
    bob, _ = await logged_in("bob")
    await check(alice, (await item(db, "pan")).id, "type_to_target", "pan")
    assert (await bob.get("/vocab/spanish/overview")).json()["groups"][0]["seen"] == 0
    assert await db.scalar(select(func.count()).select_from(VocabReview)) == 1


@pytest.mark.parametrize("method,path", [
    ("GET", "/vocab/spanish/overview"),
    ("GET", "/vocab/spanish/session"),
    ("GET", "/vocab/spanish/items"),
    ("POST", "/vocab/check"),
])
async def test_vocabulary_requires_login(client, method, path):
    assert (await client.request(method, path, json={})).status_code == 401
