"""Find the mistake: the hand-written pairs and grading a typed correction (services/grammar.py)."""
import pytest

from app.models import Exercise, ExerciseType, Language
from app.services import grammar
from app.services.grammar import Fix, find_fix, grade_answer

ES, FR, EN = Language.spanish, Language.french, Language.english


# ── The one change between two sentences ─────────────────────────────────────

def test_find_fix_lays_out_a_one_word_correction():
    assert find_fix("Tengo una libro nuevo.", "Tengo un libro nuevo.") == Fix(
        wrong="una", right="un", before="Tengo ", after=" libro nuevo.")


def test_find_fix_handles_contractions_missing_and_extra_words():
    assert find_fix("Voy a el cine.", "Voy al cine.") == Fix("a el", "al", "Voy ", " cine.")
    assert find_fix("I want go home.", "I want to go home.") == Fix("", "to", "I want ", " go home.")
    assert find_fix("I go to home.", "I go home.") == Fix("to", "", "I go ", "home.")
    assert find_fix("I am here too.", "I am here.") == Fix("too", "", "I am here ", ".")


@pytest.mark.parametrize("with_error,corrected", [
    ("Tengo un libro.", "Tengo un libro."),        # the reported bug: nothing wrong to fix
    ("tengo un libro", "Tengo un libro."),         # only capitals/punctuation differ
    ("Tengo una libro y un casa.", "Tengo un libro y una casa."),  # two mistakes
    ("A b c d e f.", "G h i j k l."),              # a rewrite, not a correction
])
def test_find_fix_needs_exactly_one_small_change(with_error, corrected):
    assert find_fix(with_error, corrected) is None


# ── The bank ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("language", [ES, FR, EN])
def test_bank_pairs_are_one_small_change_at_every_level(language):
    bank = grammar.load_bank(language)
    for level in range(1, 6):
        assert len([b for b in bank if b.level == level]) >= (16 if level >= 3 else 8), f"level {level}"
    assert len({b.id for b in bank}) == len(bank)            # answers are stored against the id
    assert len({b.correct for b in bank}) == len(bank)       # no duplicates
    for b in bank:
        assert find_fix(b.wrong, b.correct) is not None, b
        assert b.correct.rstrip()[-1] in ".!?" and len(b.correct.split()) >= 3, b
        assert b.why.strip(), b
        assert all(a != b.correct and a.rstrip()[-1] in ".!?" for a in b.also), b


# ── Grading ──────────────────────────────────────────────────────────────────

CONTENT = {
    "sentence_with_error": "Tengo una libro nuevo.",
    "corrected_sentence": "Tengo un libro nuevo.",
    "explanation": "'libro' is masculine: el libro, un libro.",
}


@pytest.mark.parametrize("answer", ["Tengo un libro nuevo.", "tengo un libro nuevo", "  Tengo   un libro nuevo !"])
def test_grading_ignores_capitals_punctuation_and_spacing(answer):
    graded = grade_answer(CONTENT, answer)
    assert graded.result == "correct" and graded.fix.right == "un"


def test_grading_accents_only_is_almost():
    content = {"sentence_with_error": "El esta aqui.", "corrected_sentence": "Él está aquí.", "explanation": ""}
    assert grade_answer(content, "El esta aqui").result == "almost"


@pytest.mark.parametrize("answer,note", [
    ("Tengo una libro nuevo.", "The mistake is still there: una → un."),
    ("Tengo un libro viejo.", "You fixed the mistake (una → un), but changed something else too."),
    ("Tengo una libro nueva.", "The mistake was: una → un."),
])
def test_grading_says_what_went_wrong(answer, note):
    graded = grade_answer(CONTENT, answer)
    assert graded.result == "wrong"
    assert graded.explanation == f"{note} 'libro' is masculine: el libro, un libro."


async def test_spanish_ra_and_se_subjunctives_are_both_right(db, spanish_verbs):
    accepted = await grammar.accepted_corrections(db, ES, "Si tuviera tiempo, viajaría más.")
    assert accepted == ["Si tuviera tiempo, viajaría más.", "Si tuviese tiempo, viajaría más."]
    content = {"sentence_with_error": "Si tendría tiempo, viajaría más.", "corrected_sentence": accepted[0], "explanation": ""}
    assert grade_answer(content, "si tuviese tiempo, viajaría más", accepted).result == "correct"
    assert grade_answer(content, "si tuviese tiempo, viajaría más").result == "wrong"  # without the twins


async def test_bank_alternatives_are_accepted(db):
    accepted = await grammar.accepted_corrections(db, ES, "La empresa para la que trabajo está en Bilbao.")
    assert "La empresa para la cual trabajo está en Bilbao." in accepted
    assert await grammar.accepted_corrections(db, FR, "Une phrase sans variante.") == ["Une phrase sans variante."]


# Exercises made before the grammar section still grade through /exercises/check

async def test_check_accepts_any_right_correction(logged_in, db, spanish_verbs):
    alice, _ = await logged_in()
    exercise = Exercise(type=ExerciseType.grammar, language=ES, difficulty=4, content={
        "sentence_with_error": "Si tendría tiempo, viajaría más.", "corrected_sentence": "Si tuviera tiempo, viajaría más.",
        "explanation": "Si + imperfect subjunctive.", "error_type": "si_clause",
    })
    db.add(exercise)
    await db.commit()
    data = (await alice.post("/exercises/check", json={"exercise_id": exercise.id, "user_answer": "Si tuviese tiempo, viajaría más."})).json()
    assert data["is_correct"] is True


def test_grading_an_older_exercise_without_one_clear_change():
    graded = grade_answer({"corrected_sentence": "Je mange des pommes."}, "Je mange des pomme.")
    assert (graded.result, graded.fix) == ("wrong", None)
    assert graded.explanation == "The corrected sentence is: 'Je mange des pommes.'."


async def test_generate_no_longer_makes_grammar_exercises(logged_in):
    alice, _ = await logged_in()
    r = await alice.post("/exercises/generate", json={"type": "grammar", "language": "spanish", "difficulty": 2})
    assert r.status_code == 400


async def test_check_returns_the_fix_and_is_lenient(logged_in, db):
    alice, _ = await logged_in()
    exercise = Exercise(type=ExerciseType.grammar, language=ES, difficulty=2, content=CONTENT)
    db.add(exercise)
    await db.commit()

    data = (await alice.post("/exercises/check", json={"exercise_id": exercise.id, "user_answer": "tengo un libro nuevo"})).json()
    assert (data["is_correct"], data["almost"]) == (True, False)
    assert data["fix"] == {"wrong": "una", "right": "un", "before": "Tengo ", "after": " libro nuevo."}

    data = (await alice.post("/exercises/check", json={"exercise_id": exercise.id, "user_answer": "Tengo una libro nuevo."})).json()
    assert data["is_correct"] is False
    assert data["explanation"].startswith("The mistake is still there: una → un.")
