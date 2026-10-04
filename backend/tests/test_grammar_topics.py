"""The grammar section: hand-written topics and sheets (services/grammar_topics.py, routers/grammar.py)."""
import json
import random
import re
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models import GrammarAttempt, GrammarReview, Language
from app.services import grammar_topics
from app.services.grammar_topics import BLANK, DATA_DIR, MISTAKES_TOPIC, REVIEW_LENGTH
from app.services.history import next_review

ES = Language.spanish
FOLDER = DATA_DIR / "spanish"
TOPIC_FILES = sorted(p for p in FOLDER.glob("*.json") if p.name != "index.json")


def answer(client, topic, qid, given):
    return client.post("/grammar/answer", json={"language": "spanish", "topic": topic, "question_id": qid, "answer": given})


def question(topic_id, qid):
    return grammar_topics.get_topic(ES, topic_id).questions()[qid]


def wrong_option(q):
    return next(o for o in q.options if o != q.answer)


async def pass_time(db, days):
    for r in (await db.execute(select(GrammarReview))).scalars():
        r.due_at -= timedelta(days=days)
    for a in (await db.execute(select(GrammarAttempt))).scalars():
        a.created_at -= timedelta(days=days)
    await db.commit()


# ── The data ─────────────────────────────────────────────────────────────────

def test_index_lists_every_category_and_topic_once():
    index = json.loads((FOLDER / "index.json").read_text(encoding="utf-8"))
    ids = [c["id"] for c in index["categories"]]
    assert len(ids) == len(set(ids))
    assert sorted(index["order"]) == sorted(p.stem for p in TOPIC_FILES)


@pytest.mark.parametrize("path", TOPIC_FILES, ids=lambda p: p.stem)
def test_topic_file_is_well_formed(path):
    index = json.loads((FOLDER / "index.json").read_text(encoding="utf-8"))
    topic = json.loads(path.read_text(encoding="utf-8"))
    assert topic["id"] == path.stem
    assert topic["category"] in {c["id"] for c in index["categories"]} - {"mixed"}
    assert topic["level"] in range(1, 6)
    assert topic["title"].strip() and topic["spanish"].strip()
    assert 2 <= len(topic["rule"]) <= 5 and all(r.strip() for r in topic["rule"])
    assert topic["sheets"]

    ids, texts = set(), set()
    for number, sheet in enumerate(topic["sheets"], 1):
        assert 10 <= len(sheet["questions"]) <= 16, f"sheet {number}"
        for q in sheet["questions"]:
            assert len(q) == 5, q  # run scripts/format_grammar_topics.py to give new questions an id
            qid, text, right, wrong, why = q
            assert re.fullmatch(r"\d+-\d{2}", qid) and qid not in ids, q
            ids.add(qid)
            assert text.count(BLANK) == 1, q
            assert text not in texts, q
            texts.add(text)
            assert len(wrong) == 3 and len({right, *wrong}) == 4, q  # four different options
            assert all(o and o.strip() == o for o in [right, *wrong]), q
            assert why.strip(), q


def test_the_bank_is_organised_like_lingua():
    bank = grammar_topics.load(ES)
    topics = list(bank.topics.values())
    assert len(topics) >= 40 and sum(len(t.sheets) for t in topics) >= 60
    # Every category has topics, and the levels run from A1 to B2
    assert {t.category for t in topics} == {c.id for c in bank.categories}
    assert {t.level for t in topics if t.level} == {1, 2, 3, 4}
    # Lingua's own topics are all here
    for lingua in ["ser-y-estar", "por-o-para", "gustar", "muy-o-mucho", "bien-o-bueno", "a-o-en",
                   "objeto-directo-o-indirecto", "imperativo", "pronombres-interrogativos", "poder-o-saber"]:
        assert lingua in bank.topics
    # Find the mistake comes last, one sheet per level, graded as typed corrections
    mistakes = topics[-1]
    assert mistakes.id == MISTAKES_TOPIC
    assert [s.title for s in mistakes.sheets] == ["A1", "A2", "B1", "B2", "C1"]
    assert all(q.kind == "correct" for q in mistakes.questions().values())


def test_options_are_shuffled_once_and_the_same_every_time():
    q = question("ser-y-estar", "1-01")
    assert sorted(q.options) == sorted(["son", "están", "es", "estamos"])
    grammar_topics.load.cache_clear()
    assert question("ser-y-estar", "1-01").options == q.options
    # The right answer isn't always in the same place
    positions = {q.options.index(q.answer) for t in grammar_topics.load(ES).topics.values()
                 for q in t.questions().values() if q.kind == "choice"}
    assert positions == {0, 1, 2, 3}


def test_a_language_without_topics_has_an_empty_bank():
    assert grammar_topics.load(Language.norwegian).topics == {}


# ── Pages ────────────────────────────────────────────────────────────────────

async def test_overview_lists_categories_topics_and_progress(logged_in):
    alice, _ = await logged_in()
    await answer(alice, "ser-y-estar", "1-01", "son")
    await answer(alice, "ser-y-estar", "1-02", wrong_option(question("ser-y-estar", "1-02")))

    data = (await alice.get("/grammar/spanish")).json()
    assert [c["id"] for c in data["categories"]][:2] == ["articles", "nouns"]
    ser = next(t for t in data["topics"] if t["id"] == "ser-y-estar")
    assert (ser["category"], ser["level"], ser["spanish"]) == ("verbs", 1, "Ser y estar")
    assert ser["sheets"][0] == {"number": 1, "title": None, "questions": 12, "answered": 2, "correct": 1}
    assert (ser["answered"], ser["correct"], ser["status"]) == (2, 1, "needs_work")
    assert data["questions"] == sum(t["questions"] for t in data["topics"])
    assert data["correct"] == 1


async def test_topic_page_has_the_rule_and_the_sheets(logged_in):
    alice, _ = await logged_in()
    data = (await alice.get("/grammar/spanish/topics/por-o-para")).json()
    assert data["title"] == "Por or para" and len(data["rule"]) >= 2
    assert [s["number"] for s in data["sheets"]] == [1, 2, 3]
    assert data["status"] is None and data["answered"] == 0


async def test_a_sheet_never_gives_away_the_answers(logged_in):
    alice, _ = await logged_in()
    data = (await alice.get("/grammar/spanish/topics/ser-y-estar/sheets/2")).json()
    assert (data["topic"], data["number"], data["sheet_count"], len(data["questions"])) == ("ser-y-estar", 2, 3, 12)
    first = data["questions"][0]
    assert set(first) == {"id", "kind", "text", "options"} and len(first["options"]) == 4


@pytest.mark.parametrize("path", [
    "/grammar/spanish/topics/nope", "/grammar/spanish/topics/ser-y-estar/sheets/9",
    "/grammar/spanish/topics/ser-y-estar/sheets/0", "/grammar/spanish/topics/nope/review",
])
async def test_unknown_topics_and_sheets(logged_in, path):
    alice, _ = await logged_in()
    assert (await alice.get(path)).status_code == 404


# ── Answering ────────────────────────────────────────────────────────────────

async def test_a_right_option(logged_in, db):
    alice, user = await logged_in()
    data = (await answer(alice, "ser-y-estar", "1-01", "son")).json()
    assert (data["result"], data["is_correct"], data["answer"]) == ("correct", True, "son")
    assert data["sentence"] == "Mis compañeros de clase son muy simpáticos."
    assert data["explanation"] == "Character: ser."
    assert data["status"] is None  # never got wrong: nothing to work on
    a = (await db.execute(select(GrammarAttempt))).scalar_one()
    assert (a.user_id, a.topic, a.question_id, a.is_correct) == (user["id"], "ser-y-estar", "1-01", True)
    assert (await db.execute(select(GrammarReview))).first() is None


async def test_a_wrong_option_gives_the_answer_and_starts_a_review(logged_in, db):
    alice, _ = await logged_in()
    data = (await answer(alice, "ser-y-estar", "1-01", "están")).json()
    assert (data["result"], data["is_correct"], data["answer"], data["status"]) == ("wrong", False, "son", "needs_work")
    review = (await db.execute(select(GrammarReview))).scalar_one()
    assert (review.topic, review.box, review.wrong_count) == ("ser-y-estar", 0, 1)


async def test_options_must_match_exactly(logged_in):
    # "a El" (El Salvador) and "a el" are different options: capitals count
    alice, _ = await logged_in()
    q = question("al-y-del", "1-08")
    assert q.answer == "a El" and "a el" in q.options
    assert (await answer(alice, "al-y-del", "1-08", "a el")).json()["result"] == "wrong"
    assert (await answer(alice, "al-y-del", "1-08", "a El")).json()["result"] == "correct"


async def test_answers_must_be_one_of_the_options(logged_in):
    alice, _ = await logged_in()
    assert (await answer(alice, "ser-y-estar", "1-01", "sois")).status_code == 422
    assert (await answer(alice, "ser-y-estar", "9-99", "son")).status_code == 404
    assert (await answer(alice, "nope", "1-01", "son")).status_code == 404


async def test_find_the_mistake_is_graded_as_a_typed_correction(logged_in):
    alice, _ = await logged_in()
    first = grammar_topics.get_topic(ES, MISTAKES_TOPIC).sheets[0].questions[0]
    assert (first.text, first.answer) == ("Mi hermano es enfermo hoy.", "Mi hermano está enfermo hoy.")

    data = (await answer(alice, MISTAKES_TOPIC, first.id, "mi hermano está enfermo hoy")).json()
    assert (data["result"], data["sentence"]) == ("correct", "Mi hermano está enfermo hoy.")
    assert data["fix"] == {"wrong": "es", "right": "está", "before": "Mi hermano ", "after": " enfermo hoy."}

    assert (await answer(alice, MISTAKES_TOPIC, first.id, "Mi hermano esta enfermo hoy.")).json()["result"] == "almost"
    data = (await answer(alice, MISTAKES_TOPIC, first.id, "Mi hermano es enfermo hoy.")).json()
    assert data["result"] == "wrong" and data["explanation"].startswith("The mistake is still there: es → está.")


async def test_the_topic_is_fixed_after_the_one_day_and_three_day_check_ups(logged_in, db):
    alice, _ = await logged_in()
    q = question("gustar", "1-01")
    assert (await answer(alice, "gustar", "1-01", wrong_option(q))).json()["status"] == "needs_work"
    assert (await answer(alice, "gustar", "1-02", "gustan")).json()["status"] == "getting_there"
    assert (await answer(alice, "gustar", "1-03", "le")).json()["status"] == "getting_there"  # same day: no credit
    assert (await db.execute(select(GrammarReview))).scalar_one().box == 1

    await pass_time(db, 1)
    assert (await answer(alice, "gustar", "1-01", "gusta")).json()["status"] == "getting_there"
    await pass_time(db, 3)
    assert (await answer(alice, "gustar", "1-01", "gusta")).json()["status"] == "fixed"


async def test_a_review_sheet_puts_last_mistakes_first(logged_in):
    alice, _ = await logged_in()
    await answer(alice, "muy-o-mucho", "1-03", "muy")        # wrong
    await answer(alice, "muy-o-mucho", "2-05", "muchas")     # wrong
    await answer(alice, "muy-o-mucho", "1-01", "muy")        # right
    await answer(alice, "muy-o-mucho", "1-04", "mucho")      # wrong, then right: not a mistake any more
    await answer(alice, "muy-o-mucho", "1-04", "muy")

    data = (await alice.get("/grammar/spanish/topics/muy-o-mucho/review")).json()
    assert (data["number"], data["title"], len(data["questions"])) == (None, "Review", REVIEW_LENGTH)
    ids = [q["id"] for q in data["questions"]]
    assert set(ids[:2]) == {"1-03", "2-05"}
    assert "1-01" not in ids and "1-04" not in ids  # 20 never-answered questions come before them


async def test_review_sheets_have_no_repeats(db):
    topic = grammar_topics.get_topic(ES, "a-o-en")
    questions = await grammar_topics.review_questions(db, 0, ES, topic, random.Random(1))
    assert len({q.id for q in questions}) == len(questions) == REVIEW_LENGTH


# ── Work on this, My mistakes, stats ─────────────────────────────────────────

async def test_mistaken_topics_show_up_in_work_on_this(logged_in):
    alice, _ = await logged_in()
    for qid in ("1-01", "1-02"):
        await answer(alice, "ser-y-estar", qid, wrong_option(question("ser-y-estar", qid)))
    await answer(alice, "gustar", "1-01", wrong_option(question("gustar", "1-01")))
    await answer(alice, "gustar", "1-02", "gustan")

    data = (await alice.get("/history/weak-spots/spanish")).json()
    assert [(t["topic"], t["status"], t["mistakes"]) for t in data["topics"]] == [
        ("ser-y-estar", "needs_work", 2), ("gustar", "getting_there", 1),
    ]
    assert data["topics"][0]["title"] == "Ser or estar"
    assert data["counts"] == {"needs_work": 1, "getting_there": 1, "fixed": 0}
    assert (data["grammar_due_count"], data["due_count"]) == (1, 0)
    assert data["next_check_up_at"] == data["topics"][1]["due_at"]


async def test_grammar_mistakes_are_in_the_history(logged_in):
    alice, _ = await logged_in()
    bob, _ = await logged_in("bob")
    await answer(alice, "ser-y-estar", "1-01", "están")
    data = (await alice.get("/history/mistakes/spanish")).json()
    [group] = data["topics"]
    assert (group["topic"], group["title"], group["status"], group["total_mistakes"]) == (
        "ser-y-estar", "Ser or estar", "needs_work", 1)
    assert group["mistakes"][0] | {"created_at": None} == {
        "question": "Mis compañeros de clase ___ muy simpáticos.", "user_answer": "están",
        "expected": "son", "is_almost": False, "created_at": None,
    }
    assert data["counts"]["needs_work"] == 1
    assert (await bob.get("/history/mistakes/spanish")).json()["topics"] == []


async def test_grammar_answers_count_toward_the_daily_goal(logged_in):
    alice, _ = await logged_in()
    await answer(alice, "ser-y-estar", "1-01", "son")
    await answer(alice, "ser-y-estar", "1-02", "es")
    stats = (await alice.get("/history/stats?language=spanish&days=7")).json()
    assert (stats["total"], stats["correct"], stats["today_count"]) == (2, 1, 2)


async def test_answers_are_per_user(logged_in):
    alice, _ = await logged_in()
    bob, _ = await logged_in("bob")
    await answer(alice, "ser-y-estar", "1-01", "son")
    assert (await bob.get("/grammar/spanish")).json()["correct"] == 0


@pytest.mark.parametrize("method,path", [
    ("GET", "/grammar/spanish"),
    ("GET", "/grammar/spanish/topics/ser-y-estar"),
    ("GET", "/grammar/spanish/topics/ser-y-estar/sheets/1"),
    ("GET", "/grammar/spanish/topics/ser-y-estar/review"),
    ("POST", "/grammar/answer"),
])
async def test_grammar_requires_login(client, method, path):
    assert (await client.request(method, path, json={})).status_code == 401


def test_topics_share_the_verb_review_schedule():
    # A right answer before the check-up changes nothing, as for verbs
    now = datetime(2026, 10, 4, 12, tzinfo=timezone.utc)
    assert next_review(1, now + timedelta(days=1), True, now) == (1, now + timedelta(days=1))
