from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, and_, func
from app.models import VerbConjugation, Language

# Known alternate forms: add entries here to propagate everywhere (display, checking, VerbTable).
FORM_ALTERNATES: dict[str, list[str]] = {
    "hay": ["ha"],
    "ha":  ["hay"],
}

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
