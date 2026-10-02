import pytest

from app.services.explain import regular_guess, tense_name
from app.services.grading import fold_accents, grade, normalize


def test_normalize_ignores_case_and_spacing():
    assert normalize("  He   Tenido ") == "he tenido"


@pytest.mark.parametrize("text,folded", [
    ("tuvó", "tuvo"), ("está", "esta"), ("niño", "nino"), ("pingüino", "pinguino"),
    ("garçon", "garcon"), ("Été", "ete"),
])
def test_fold_accents(text, folded):
    assert fold_accents(text) == folded


@pytest.mark.parametrize("answer,accepted,result,matched", [
    ("tuvo", ["tuvo"], "correct", "tuvo"),
    (" TUVO ", ["tuvo"], "correct", "tuvo"),
    ("tuvó", ["tuvo"], "almost", "tuvo"),      # accent added
    ("hable", ["hablé"], "almost", "hablé"),   # accent missing (and it matters: hable ≠ hablé)
    ("tuve", ["tuvo"], "wrong", None),
    ("", ["tuvo"], "wrong", None),
    ("   ", ["tuvo"], "wrong", None),
])
def test_grade(answer, accepted, result, matched):
    g = grade(answer, accepted)
    assert (g.result, g.matched) == (result, matched)
    assert g.is_correct == (result == "correct")
    assert g.is_almost == (result == "almost")


def test_grade_accepts_any_alternate_and_prefers_exact_matches():
    assert grade("tuviese", ["tuviera", "tuviese"]).result == "correct"
    # "esta" exactly matches the second form, so it isn't an "almost" for "está"
    assert grade("esta", ["está", "esta"]).result == "correct"


def test_regular_guess():
    assert regular_guess("tener", "comer", "comió") == "tenió"
    assert regular_guess("cantar", "hablar", "he hablado") == "he cantado"
    assert regular_guess("tener", "comer", "xyz") is None


def test_tense_name():
    assert tense_name("Indicativo", "Indicativo pretérito imperfecto") == "pretérito imperfecto (indicativo)"
    assert tense_name("Subjuntivo", "Subjuntivo pretérito imperfecto (2)") == "pretérito imperfecto (subjuntivo)"
    assert tense_name("Condicional", "Condicional") == "condicional"
    assert tense_name("Subjonctif", "Présent") == "présent (subjonctif)"
