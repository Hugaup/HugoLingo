"""One-line, rule-based explanations for conjugation mistakes.

No LLM, so they're instant. The first rule that applies wins:
  1. accent-only slip ("almost")
  2. the answer is another person's form in the same tense
  3. the answer is a form of this verb from a different tense
  4. the verb breaks the regular pattern here (compared with a model regular verb)
  5. otherwise, spell out the regular pattern
Every explanation also carries the whole tense, for the "show all forms" toggle.
"""
import os

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Language, VerbConjugation
from app.services.conjugation_utils import PRONOUNS, canonical_tense, tense_table, variant_tense_names
from app.services.grading import Grade, normalize

# A textbook regular verb per infinitive ending, to tell regular forms from irregular ones
REGULAR_MODELS: dict[Language, dict[str, str]] = {
    Language.spanish: {"ar": "hablar", "er": "comer", "ir": "vivir"},
    Language.french: {"er": "parler", "ir": "finir", "re": "vendre"},
}


def tense_name(mood: str, tense: str) -> str:
    """Readable tense name: 'Indicativo pretérito imperfecto' → 'pretérito imperfecto (indicativo)'."""
    name = canonical_tense(tense)
    if name.lower().startswith(mood.lower() + " "):
        name = name[len(mood) + 1:]
    return name.lower() if name.lower() == mood.lower() else f"{name.lower()} ({mood.lower()})"


def regular_guess(verb: str, model: str, model_form: str) -> str | None:
    """What `verb` would be if it conjugated exactly like `model` (hablar → hablé ⇒ cantar → canté)."""
    verb_stem, model_stem = verb[:-2], model[:-2]
    at = model_form.lower().find(model_stem.lower())
    if at < 0:
        return None
    return model_form[:at] + verb_stem + model_form[at + len(model_stem):]


async def explain_mistake(
    db: AsyncSession,
    language: Language,
    verb: str,
    mood: str,
    tense: str,
    person: str,
    answer: str,
    graded: Grade,
    expected: str,
) -> dict:
    table = await tense_table(db, language, verb, mood, tense)
    pronouns = PRONOUNS.get(language, {})
    pronoun = lambda p: pronouns.get(p, p)  # noqa: E731
    given = normalize(answer)

    if graded.is_almost:
        summary = f"Almost — just the accents: it's “{graded.matched or expected}”."
    elif others := [p for p, forms in table.items() if p != person and given in map(normalize, forms)]:
        summary = f"“{answer}” is the {pronoun(others[0])} form — for {pronoun(person)} it's “{expected}”."
    elif other := await _other_tense_of(db, language, verb, mood, tense, given):
        summary = (
            f"“{answer}” is the {tense_name(*other)} — "
            f"this one needs the {tense_name(mood, tense)}: “{expected}”."
        )
    else:
        summary = await _pattern_note(db, language, verb, mood, tense, person, expected, table, pronoun)

    return {
        "summary": summary,
        "mood": mood,
        "tense": canonical_tense(tense),
        "forms": [{"person": p, "form": forms[0]} for p, forms in table.items()],
    }


async def _other_tense_of(
    db: AsyncSession, language: Language, verb: str, mood: str, tense: str, given: str,
) -> tuple[str, str] | None:
    row = (await db.execute(
        select(VerbConjugation.mood, VerbConjugation.tense)
        .where(
            VerbConjugation.language == language,
            func.lower(VerbConjugation.verb_infinitive) == verb.lower(),
            func.lower(VerbConjugation.form) == given,
            ~(
                (func.lower(VerbConjugation.mood) == mood.lower())
                & func.lower(VerbConjugation.tense).in_([t.lower() for t in variant_tense_names(canonical_tense(tense))])
            ),
        )
        .order_by(VerbConjugation.mood, VerbConjugation.tense)
        .limit(1)
    )).first()
    return (row.mood, row.tense) if row else None


async def _pattern_note(db, language, verb, mood, tense, person, expected, table, pronoun) -> str:
    ending = verb[-2:].lower()
    model = REGULAR_MODELS.get(language, {}).get(ending)
    if not model:
        return f"The correct form is “{expected}”."

    stem = os.path.commonprefix([forms[0].lower() for p, forms in table.items() if p != "—"])
    stem_note = f" Its stem in this tense is {stem}-." if len(stem) >= 2 and not verb.lower().startswith(stem) else ""

    if len(verb) <= 2:
        # A bare ending (ir) has no stem to build a "regular" guess from
        return f"{verb} is irregular here.{stem_note}"
    if verb.lower() == model:
        guess = expected
    else:
        model_forms = (await tense_table(db, language, model, mood, tense, person)).get(person)
        guess = regular_guess(verb, model, model_forms[0]) if model_forms else None
    if guess is None:
        return f"The correct form is “{expected}”."

    if normalize(guess) != normalize(expected):
        return f"{verb} doesn't follow the regular -{ending} pattern here (that would give “{guess}”).{stem_note}"

    verb_stem = verb[:-2]
    if expected.lower().startswith(verb_stem.lower()) and len(expected) > len(verb_stem):
        return f"Regular -{ending} verb: {verb_stem}- + “-{expected[len(verb_stem):]}” for {pronoun(person)}."
    return f"Regular -{ending} verb, like {model}: “{expected}”."
