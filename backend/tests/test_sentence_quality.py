"""Server-side blanking and quality checks, using real failures seen in docs/llm-benchmark.md."""
import pytest

from app.models import Language, VerbConjugation
from app.services.sentences import blank_out, quality_problem, verb_forms

LIMPIAR_FORMS = {"limpiar", "limpio", "limpias", "limpia", "limpiaré", "limpiarás", "limpié"}
CREER_FORMS = {"creer", "creo", "crees", "cree", "creara", "creyó"}


# ── Blanking ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("sentence,forms,expected", [
    ("Mañana yo limpiaré la casa.", ["limpiaré"], "Mañana yo ___ la casa."),
    ("Limpiaré la casa mañana.", ["limpiaré"], "___ la casa mañana."),                    # any case
    ("Hoy ya he comido en casa.", ["he comido"], "Hoy ya ___ en casa."),                  # compound tense
    ("Hoy ya he   comido en  casa.", ["he comido"], "Hoy ya ___ en casa."),               # messy spacing
    ("Ojalá yo tuviese más tiempo.", ["tuviera", "tuviese"], "Ojalá yo ___ más tiempo."),  # alternate spelling
    ("Ella comenzó a comer temprano.", ["come"], None),        # only inside other words → missing
    ("Yo como y como sin parar.", ["como"], None),             # twice → ambiguous blank
    ("Vosotros comprabaréis zapatos.", ["compraréis"], None),  # model misspelt the form
    ("Ojalá tuviera o tuviese suerte.", ["tuviera", "tuviese"], None),
])
def test_blank_out(sentence, forms, expected):
    assert blank_out(sentence, forms) == expected


# ── Quality checks ───────────────────────────────────────────────────────────

def test_a_good_sentence_passes():
    s = "Mañana yo ___ la casa porque voy a salir de viaje."
    assert quality_problem(s, "yo", LIMPIAR_FORMS, Language.spanish, "1s") is None


@pytest.mark.parametrize("blanked,subject,forms,person,problem", [
    ("Esta semana ___.", "él", LIMPIAR_FORMS, "3s", "too short"),
    ("Mañana yo ___ la casa con mi hermano", "yo", LIMPIAR_FORMS, "1s", "not a full sentence"),
    ("Yo ___ mañana limpiaré la casa entera.", "yo", LIMPIAR_FORMS, "1s", "another form of the same verb"),
    ("Ojalá ___ creara más tiempo para leer.", "él", CREER_FORMS, "3s", "another form of the same verb"),
    ("Él ___ ___ por la ciudad esta semana.", "él", LIMPIAR_FORMS, "3s", "blank"),
    ("Mañana nosotros ___ la casa entera.", "nosotros", LIMPIAR_FORMS, "1s", "wrong person"),
    ("Mañana ___ la casa entera, por fin.", "", LIMPIAR_FORMS, "1s", "no subject"),
])
def test_quality_problems(blanked, subject, forms, person, problem):
    assert quality_problem(blanked, subject, forms, Language.spanish, person) == problem


async def test_verb_forms_come_from_the_database_minus_ambiguous_words(db, spanish_verbs):
    forms = await verb_forms(db, Language.spanish, "comer")
    assert {"comer", "comí", "comemos", "comieron"} <= forms
    assert "como" not in forms  # "como" (as/like) is too common to count as a repeat of comer
    s = "Como siempre, nosotros ___ a las dos en casa."
    assert quality_problem(s, "nosotros", forms, Language.spanish, "1p") is None


# ── Verb table: random verbs are everyday verbs ──────────────────────────────

async def test_random_verbs_prefer_everyday_verbs(logged_in, db, spanish_verbs):
    db.add(VerbConjugation(language=Language.spanish, verb_infinitive="zarambutear",
                           mood="Indicativo", tense="Indicativo presente", person="1s", form="zarambuteo"))
    await db.commit()
    alice, _ = await logged_in()
    for _ in range(10):
        verbs = (await alice.get("/verbs/random/spanish?count=3&mode=random")).json()
        assert len(verbs) == 3 and "zarambutear" not in verbs
    assert (await alice.get("/verbs/random/spanish?count=1&mode=endings&endings=ar")).json() == ["hablar"]
