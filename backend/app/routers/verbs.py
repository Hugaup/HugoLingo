from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, distinct, or_
from typing import Optional
import random as _random

from app.database import get_db
from app.models import VerbConjugation, Language
from app.services.conjugation_utils import COMPOUND_AUX_MAP, FORM_ALTERNATES, load_haber_forms

router = APIRouter(prefix="/verbs", tags=["verbs"])

IRREGULAR_VERBS: dict[Language, set[str]] = {
    Language.french: {
        "être", "avoir", "aller", "faire", "pouvoir", "vouloir", "savoir", "devoir",
        "voir", "venir", "prendre", "mettre", "dire", "partir", "sortir", "courir",
        "rire", "vivre", "écrire", "lire", "conduire", "naître", "mourir", "boire",
        "croire", "suivre", "connaître", "plaire", "vaincre", "résoudre", "battre",
        "valoir", "recevoir", "tenir", "peindre", "craindre", "éteindre", "joindre",
    },
    Language.spanish: {
        "ser", "estar", "ir", "tener", "hacer", "poder", "querer", "saber", "venir",
        "poner", "decir", "dar", "traer", "caber", "haber", "salir", "oír", "caer",
        "producir", "conducir", "traducir", "conocer", "reír", "dormir", "sentir",
        "pedir", "morir", "jugar", "construir", "huir", "seguir", "elegir", "volver",
        "coger", "exigir", "ver", "leer", "creer",
    },
    Language.english: {
        "be", "have", "do", "go", "see", "get", "make", "know", "take", "come",
        "say", "give", "find", "think", "tell", "become", "leave", "put", "feel",
        "bring", "begin", "keep", "hold", "write", "stand", "hear", "spend", "meet",
        "run", "lose", "send", "win", "build", "fall", "drive", "fly", "cut",
        "break", "catch", "draw", "choose", "buy", "sell", "speak", "ring", "sing",
        "swim", "wake", "shake", "sleep", "drink", "eat", "read", "sit", "set",
    },
}

VERB_ENDINGS: dict[Language, list[str]] = {
    Language.french: ["-er", "-ir", "-re"],
    Language.spanish: ["-ar", "-er", "-ir"],
    Language.english: [],
}


@router.get("/search/{language}")
async def search_verbs(
    language: Language,
    q: str = Query(..., min_length=1),
    limit: int = Query(20, le=50),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(distinct(VerbConjugation.verb_infinitive))
        .where(
            VerbConjugation.language == language,
            func.lower(VerbConjugation.verb_infinitive).startswith(q.lower()),
        )
        .order_by(VerbConjugation.verb_infinitive)
        .limit(limit)
    )
    return result.scalars().all()


@router.get("/tenses/{language}")
async def get_tenses(language: Language, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(VerbConjugation.mood, VerbConjugation.tense)
        .where(VerbConjugation.language == language, VerbConjugation.person != "—")
        .distinct()
        .order_by(VerbConjugation.mood, VerbConjugation.tense)
    )
    rows = result.all()
    # Deduplicate case-insensitively (Spanish has mixed-case duplicates)
    seen: set[tuple[str, str]] = set()
    tenses = []
    for mood, tense in rows:
        key = (mood.lower(), tense.lower())
        if key not in seen:
            seen.add(key)
            tenses.append({"mood": mood, "tense": tense})
    return tenses


@router.get("/endings/{language}")
async def get_endings(language: Language):
    return VERB_ENDINGS.get(language, [])


@router.get("/random/{language}")
async def get_random_verbs(
    language: Language,
    count: int = Query(3, ge=1, le=10),
    mode: str = Query("random"),
    endings: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    if mode == "irregular":
        pool = list(IRREGULAR_VERBS.get(language, set()))
        if not pool:
            raise HTTPException(400, "No irregular verb list for this language")
        # Verify these verbs exist in the DB
        result = await db.execute(
            select(distinct(VerbConjugation.verb_infinitive))
            .where(
                VerbConjugation.language == language,
                VerbConjugation.verb_infinitive.in_(pool),
            )
        )
        available = result.scalars().all()
        return _random.sample(available, min(count, len(available)))

    query = select(distinct(VerbConjugation.verb_infinitive)).where(
        VerbConjugation.language == language
    )
    if mode == "endings" and endings:
        ending_list = [e.strip().lstrip("-") for e in endings.split(",")]
        query = query.where(
            or_(*[VerbConjugation.verb_infinitive.like(f"%{e}") for e in ending_list])
        )

    result = await db.execute(query.order_by(func.random()).limit(count))
    return result.scalars().all()


@router.get("/table/{language}/{infinitive}")
async def get_conjugation_table(
    language: Language,
    infinitive: str,
    moods: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    query = select(VerbConjugation).where(
        VerbConjugation.language == language,
        func.lower(VerbConjugation.verb_infinitive) == infinitive.lower(),
        VerbConjugation.person != "—",
    )
    if moods:
        mood_list = [m.strip() for m in moods.split(",")]
        query = query.where(VerbConjugation.mood.in_(mood_list))

    result = await db.execute(
        query.order_by(VerbConjugation.mood, VerbConjugation.tense, VerbConjugation.person)
    )
    rows = result.scalars().all()

    if not rows:
        raise HTTPException(404, f"Verb '{infinitive}' not found for {language.value}")

    # For Spanish, resolve compound tense auxiliaries (e.g. "hablado" → "he hablado")
    haber_forms: dict = {}
    if language == Language.spanish:
        needed = {COMPOUND_AUX_MAP[r.tense.lower()] for r in rows if r.tense.lower() in COMPOUND_AUX_MAP}
        if needed:
            haber_forms = await load_haber_forms(db, language, needed)

    table: dict = {}
    for row in rows:
        form = row.form
        if haber_forms:
            aux = COMPOUND_AUX_MAP.get(row.tense.lower())
            if aux:
                haber_form = haber_forms.get((*aux, row.person))
                if haber_form:
                    form = f"{haber_form} {form}"
        table.setdefault(row.mood, {}).setdefault(row.tense, []).append(
            {"person": row.person, "form": form, "alternates": FORM_ALTERNATES.get(form.lower(), [])}
        )

    return {"infinitive": infinitive, "language": language.value, "table": table}
