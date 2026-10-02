from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, and_, func
from app.models import VerbConjugation, Language

# Known alternate forms: add entries here to propagate everywhere (display, checking, VerbTable).
FORM_ALTERNATES: dict[str, list[str]] = {
    "hay": ["ha"],
    "ha":  ["hay"],
}

def canonical_tense(tense: str) -> str:
    """Collapse Spanish subjunctive imperfecto/pluscuamperfecto "(1)"/"(2)" suffixes
    (interchangeable -ra vs -se spellings, e.g. hablara/hablase) into one shared
    tense name — they're two spellings of the same tense, not separate tenses."""
    if tense.endswith(" (1)") or tense.endswith(" (2)"):
        return tense[:-4]
    return tense


def variant_tense_names(canonical: str) -> list[str]:
    """DB-level tense name(s) a canonical (suffix-stripped) tense may be stored under."""
    return [canonical, f"{canonical} (1)", f"{canonical} (2)"]


COMPOUND_AUX_MAP: dict[str, tuple[str, str]] = {
    "indicativo pretérito perfecto compuesto":    ("indicativo", "indicativo presente"),
    "indicativo pretérito pluscuamperfecto":       ("indicativo", "indicativo pretérito imperfecto"),
    "indicativo pretérito anterior":               ("indicativo", "indicativo pretérito perfecto simple"),
    "indicativo futuro perfecto":                  ("indicativo", "indicativo futuro"),
    "condicional perfecto":                        ("condicional", "condicional"),
    "subjuntivo pretérito perfecto":               ("subjuntivo", "subjuntivo presente"),
    "subjuntivo pretérito pluscuamperfecto (1)":   ("subjuntivo", "subjuntivo pretérito imperfecto (1)"),
    "subjuntivo pretérito pluscuamperfecto (2)":   ("subjuntivo", "subjuntivo pretérito imperfecto (2)"),
    "subjuntivo futuro perfecto":                  ("subjuntivo", "subjuntivo futuro"),
}


async def load_haber_forms(
    db: AsyncSession,
    language: Language,
    needed: set[tuple[str, str]],
) -> dict[tuple[str, str, str], str]:
    """Batch-load haber auxiliary forms for a set of (mood_lower, tense_lower) pairs."""
    if not needed:
        return {}
    conditions = [
        and_(func.lower(VerbConjugation.mood) == m, func.lower(VerbConjugation.tense) == t)
        for m, t in needed
    ]
    result = await db.execute(
        select(VerbConjugation).where(
            VerbConjugation.language == language,
            VerbConjugation.verb_infinitive == "haber",
            or_(*conditions),
        )
    )
    forms: dict[tuple[str, str, str], str] = {}
    for h in result.scalars().all():
        # "hay" is haber's impersonal present; compound tenses need "ha"
        form = "ha" if h.form == "hay" else h.form
        forms[(h.mood.lower(), h.tense.lower(), h.person)] = form
    return forms


async def expected_forms(
    db: AsyncSession,
    language: Language,
    verb: str,
    mood: str,
    tense: str,
    person: str,
) -> list[str]:
    """Every accepted answer for one prompt, primary form first.

    `tense` may be canonical (suffix-stripped): both "(1)"/"(2)" spellings are
    accepted. Compound tenses are resolved to auxiliary + participle, and
    FORM_ALTERNATES are included. Empty list if the prompt doesn't exist.
    """
    result = await db.execute(
        select(VerbConjugation)
        .where(
            VerbConjugation.language == language,
            func.lower(VerbConjugation.verb_infinitive) == verb.lower(),
            func.lower(VerbConjugation.mood) == mood.lower(),
            func.lower(VerbConjugation.tense).in_([t.lower() for t in variant_tense_names(canonical_tense(tense))]),
            VerbConjugation.person == person,
        )
        .order_by(VerbConjugation.tense)
    )
    forms: list[str] = []
    for row in result.scalars().all():
        form = await resolve_compound_form(db, language, row.tense, row.person, row.form)
        for candidate in [form, *FORM_ALTERNATES.get(form.lower(), [])]:
            if candidate.lower() not in (f.lower() for f in forms):
                forms.append(candidate)
    return forms


async def resolve_compound_form(
    db: AsyncSession,
    language: Language,
    tense: str,
    person: str,
    participle: str,
) -> str:
    """Return the full compound form (auxiliary + participle), or just participle if not compound."""
    if language != Language.spanish:
        return participle
    aux = COMPOUND_AUX_MAP.get(tense.lower())
    if not aux:
        return participle
    haber_forms = await load_haber_forms(db, language, {aux})
    haber_form = haber_forms.get((*aux, person))
    if not haber_form:
        return participle
    return f"{haber_form} {participle}"
