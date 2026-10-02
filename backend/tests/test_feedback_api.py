"""Almost-right grading and compact mistake explanations across the practice areas."""
import pytest
from sqlalchemy import select

from app.models import Attempt, Exercise, ExerciseType, Language
from app.services import llm

PRETERITO = {"mood": "Indicativo", "tense": "Indicativo pretérito perfecto simple"}
IMPERFECTO = {"mood": "Indicativo", "tense": "Indicativo pretérito imperfecto"}


def drill(verb, person, answer, tense=PRETERITO):
    return {"language": "spanish", "verb_infinitive": verb, "person": person, "answer": answer, **tense}


async def check(client, *args, **kwargs):
    r = await client.post("/history/drill/check", json=drill(*args, **kwargs))
    assert r.status_code == 200, r.text
    return r.json()


# ── Almost right ─────────────────────────────────────────────────────────────

async def test_accent_slip_is_almost_but_logged_as_a_mistake(logged_in, spanish_verbs, db):
    alice, _ = await logged_in()
    data = await check(alice, "tener", "1s", "tuvé")
    assert (data["result"], data["is_correct"], data["expected"]) == ("almost", False, "tuve")
    assert data["explanation"]["summary"] == "Almost — just the accents: it's “tuve”."

    a = (await db.execute(select(Attempt))).scalar_one()
    assert (a.is_correct, a.is_almost) == (False, True)
    # ...and it still feeds the weak spots like any other mistake
    weak = (await alice.get("/history/weak-spots/spanish")).json()
    assert weak["combos"][0]["mistakes"] == 1


async def test_correct_answers_are_never_flagged_almost(logged_in, spanish_verbs, db):
    alice, _ = await logged_in()
    data = await check(alice, "tener", "1s", "tuve")
    assert (data["result"], data["explanation"]) == ("correct", None)
    assert (await db.execute(select(Attempt.is_almost))).scalar_one() is False


# ── Explanations ─────────────────────────────────────────────────────────────

async def test_explains_an_irregular_verb_with_the_regular_guess_and_new_stem(logged_in, spanish_verbs):
    alice, _ = await logged_in()
    exp = (await check(alice, "tener", "3s", "tenió"))["explanation"]
    assert exp["summary"] == (
        "tener doesn't follow the regular -er pattern here (that would give “tenió”). "
        "Its stem in this tense is tuv-."
    )
    assert exp["forms"] == [
        {"person": p, "form": f}
        for p, f in zip(["1s", "2s", "3s", "1p", "2p", "3p"], ["tuve", "tuviste", "tuvo", "tuvimos", "tuvisteis", "tuvieron"])
    ]
    assert (exp["mood"], exp["tense"]) == (PRETERITO["mood"], PRETERITO["tense"])


async def test_explains_when_the_answer_is_another_persons_form(logged_in, spanish_verbs):
    alice, _ = await logged_in()
    exp = (await check(alice, "tener", "3s", "tuve"))["explanation"]
    assert exp["summary"] == "“tuve” is the yo form — for él/ella it's “tuvo”."


async def test_explains_when_the_answer_is_from_another_tense(logged_in, spanish_verbs):
    alice, _ = await logged_in()
    exp = (await check(alice, "tener", "1s", "tenía"))["explanation"]
    assert exp["summary"] == (
        "“tenía” is the pretérito imperfecto (indicativo) — "
        "this one needs the pretérito perfecto simple (indicativo): “tuve”."
    )


async def test_two_letter_verbs_get_no_nonsense_regular_guess(logged_in, spanish_verbs):
    alice, _ = await logged_in()
    exp = (await check(alice, "ir", "3s", "iró"))["explanation"]
    assert exp["summary"] == "ir is irregular here. Its stem in this tense is fu-."


async def test_spells_out_the_pattern_for_a_regular_verb(logged_in, spanish_verbs):
    alice, _ = await logged_in()
    exp = (await check(alice, "hablar", "1s", "hablí"))["explanation"]
    assert exp["summary"] == "Regular -ar verb: habl- + “-é” for yo."


# ── Sentence completion ──────────────────────────────────────────────────────

ITEM = {
    "sentence": "Ayer yo ___ mucho trabajo.", "subject_hint": "yo", "verb_infinitive": "tener",
    **PRETERITO, "person": "1s", "correct_form": "tuve", "alternates": [],
}


@pytest.fixture
def fake_llm(monkeypatch):
    async def chat(messages):
        return "Longer AI explanation."
    monkeypatch.setattr(llm.llm_client, "chat", chat)


async def sentence(client, user_form, mood_tense=PRETERITO):
    r = await client.post("/conjugation-exercises/sentence/check", json={
        "item": ITEM, "user_form": user_form, "language": "spanish",
        "user_mood": mood_tense["mood"], "user_tense": mood_tense["tense"],
    })
    assert r.status_code == 200, r.text
    return r.json()


async def test_sentence_accent_slip_is_almost(logged_in, spanish_verbs, fake_llm, db):
    alice, _ = await logged_in()
    data = await sentence(alice, "tuvé")
    assert (data["form_result"], data["form_correct"], data["tense_correct"]) == ("almost", False, True)
    assert data["hint"]["summary"].startswith("Almost")
    assert data["explanation"] == "Longer AI explanation."
    a = (await db.execute(select(Attempt))).scalar_one()
    assert (a.is_correct, a.is_almost) == (False, True)


async def test_sentence_right_form_wrong_tense_gets_a_tense_hint(logged_in, spanish_verbs, fake_llm):
    alice, _ = await logged_in()
    data = await sentence(alice, "tuve", IMPERFECTO)
    assert (data["form_result"], data["tense_correct"]) == ("correct", False)
    assert data["hint"]["summary"] == (
        "Right form — but it's the pretérito perfecto simple (indicativo), not the pretérito imperfecto (indicativo)."
    )
    assert len(data["hint"]["forms"]) == 6


async def test_sentence_fully_correct_has_no_hint(logged_in, spanish_verbs, fake_llm):
    alice, _ = await logged_in()
    data = await sentence(alice, "tuve")
    assert (data["form_result"], data["hint"]) == ("correct", None)


# ── Old exercise flow and the browser-graded verb table ──────────────────────

@pytest.mark.parametrize("ex_type,content,answer", [
    (ExerciseType.conjugation,
     {"sentence": "Ayer ___ frío.", "verb_infinitive": "tener", "correct_answer": "tuve", "tense": "past", "subject": "yo", "explanation": "Pretérito."},
     "tuvé"),
    (ExerciseType.grammar,
     {"sentence_with_error": "El esta aqui.", "corrected_sentence": "Él está aquí.", "explanation": "Accents."},
     "El esta aqui."),
])
async def test_old_exercise_flow_reports_almost(logged_in, db, ex_type, content, answer):
    alice, _ = await logged_in()
    exercise = Exercise(type=ex_type, language=Language.spanish, difficulty=2, content=content)
    db.add(exercise)
    await db.commit()

    data = (await alice.post("/exercises/check", json={"exercise_id": exercise.id, "user_answer": answer})).json()
    assert (data["is_correct"], data["almost"]) == (False, True)
    assert data["explanation"].startswith("Almost — just the accents.")


async def test_old_exercise_flow_wrong_is_not_almost(logged_in, db):
    alice, _ = await logged_in()
    exercise = Exercise(type=ExerciseType.conjugation, language=Language.spanish, difficulty=2, content={
        "sentence": "Ayer ___ frío.", "verb_infinitive": "tener", "correct_answer": "tuve", "tense": "past",
        "subject": "yo", "explanation": "Pretérito.",
    })
    db.add(exercise)
    await db.commit()
    data = (await alice.post("/exercises/check", json={"exercise_id": exercise.id, "user_answer": "tenía"})).json()
    assert (data["is_correct"], data["almost"]) == (False, False)


async def test_verb_table_reports_almost(logged_in, db):
    alice, _ = await logged_in()
    await alice.post("/history/attempts", json={"language": "spanish", "source": "verb_table", "attempts": [
        {"verb_infinitive": "tener", **PRETERITO, "person": "1s", "user_answer": "tuvé", "expected": "tuve",
         "is_correct": False, "is_almost": True},
        # is_almost is meaningless on a right answer and is dropped
        {"verb_infinitive": "tener", **PRETERITO, "person": "2s", "user_answer": "tuviste", "expected": "tuviste",
         "is_correct": True, "is_almost": True},
    ]})
    rows = (await db.execute(select(Attempt).order_by(Attempt.person))).scalars().all()
    assert [(a.person, a.is_correct, a.is_almost) for a in rows] == [("1s", False, True), ("2s", True, False)]
