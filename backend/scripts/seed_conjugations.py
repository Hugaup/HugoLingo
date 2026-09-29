#!/usr/bin/env python3
"""Seed verb_conjugations table using mlconjug3's built-in JSON data files.

Reads the raw conjugation JSON data directly — no ML model is loaded.
Run from the backend/ directory:
    source .venv/bin/activate
    python scripts/seed_conjugations.py
"""
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.dialects.postgresql import insert as pg_insert

import mlconjug3
from app.database import AsyncSessionLocal
from app.models import Language, VerbConjugation

DATA_DIR = Path(mlconjug3.__file__).parent / "data" / "conjug_manager"

LANG_CODES = {
    Language.french: "fr",
    Language.spanish: "es",
    Language.english: "en",
}

PERSON_LABELS = {0: "1s", 1: "2s", 2: "3s", 3: "1p", 4: "2p", 5: "3p"}

# mlconjug3 quirks: the imperative mood has no 1st-person-singular form in
# either language (you can't command yourself), so it's indexed as a compact
# list starting at 0 rather than the standard 6-slot index starting at "yo"/"je".
IMPERATIVE_MOOD: dict[Language, str] = {
    Language.spanish: "imperativo",
    Language.french: "imperatif",
}
IMPERATIVE_PERSON_LABELS: dict[Language, dict[int, str]] = {
    # Spanish "Imperativo" covers both the affirmative and negative tense —
    # 5-slot: 0=tú, 1=él/usted, 2=nosotros, 3=vosotros, 4=ellos/ustedes.
    Language.spanish: {0: "2s", 1: "3s", 2: "1p", 3: "2p", 4: "3p"},
    # French "Imperatif Présent" — 3-slot: 0=tu, 1=nous, 2=vous.
    Language.french: {0: "2s", 1: "1p", 2: "2p"},
}

# Moods whose list entries aren't separate person-conjugated forms — only the
# first entry is a real, displayable form, and it isn't person-conjugated.
NON_PERSONAL_LIST_MOODS: dict[Language, set[str]] = {
    # Spanish "Infinitivo"/"Gerundio" list a second entry that's internal
    # bookkeeping for building compound tenses elsewhere (just the past
    # participle repeated); "Participo" is itself just that one entry.
    Language.spanish: {"infinitivo", "gerundio", "participo"},
    # French "Participe Passé" lists masculine/feminine, singular/plural
    # agreement variants, not persons — keep only the masculine singular form.
    Language.french: {"participe"},
}

BATCH_SIZE = 1000


def normalize_tense(language: Language, tense: str) -> str:
    """mlconjug3's Spanish data has inconsistent capitalization across templates
    (e.g. defective verbs like "garantir" use "Indicativo Presente" while regular
    verbs use "Indicativo presente" for the same tense) — lowercase everything
    but the first word so they collapse to one canonical name."""
    if language != Language.spanish:
        return tense
    words = tense.split(" ")
    return words[0] + "".join(" " + w.lower() for w in words[1:])


def build_rows(language: Language, lang_code: str, mood_filter: set[str] | None = None) -> list[dict]:
    verbs_path = DATA_DIR / f"verbs-{lang_code}.json"
    conjug_path = DATA_DIR / f"conjugation-{lang_code}.json"

    with open(verbs_path, encoding="utf-8") as f:
        verbs = json.load(f)
    with open(conjug_path, encoding="utf-8") as f:
        templates = json.load(f)

    rows = []
    for infinitive, verb_info in verbs.items():
        root = verb_info.get("root", "")
        template_name = verb_info.get("template", "")
        template = templates.get(template_name)
        if template is None:
            continue

        for mood, tenses in template.items():
            if not isinstance(tenses, dict):
                continue
            if mood_filter is not None and mood.lower() not in mood_filter:
                continue
            is_imperative = mood.lower() == IMPERATIVE_MOOD.get(language)
            is_non_personal_list = mood.lower() in NON_PERSONAL_LIST_MOODS.get(language, set())

            for tense, forms in tenses.items():
                tense = normalize_tense(language, tense)
                if isinstance(forms, str):
                    # Single form (e.g. Participe Présent: "aimant")
                    form = root + forms
                    rows.append({
                        "language": language,
                        "verb_infinitive": infinitive,
                        "mood": mood,
                        "tense": tense,
                        "person": "—",
                        "form": form,
                    })
                elif isinstance(forms, list):
                    for i, entry in enumerate(forms):
                        if is_non_personal_list and i > 0:
                            continue
                        if not isinstance(entry, list) or len(entry) < 2:
                            continue
                        person_idx, suffix = entry[0], entry[1]
                        if suffix is None:
                            continue
                        form = root + suffix
                        if is_non_personal_list:
                            person = "—"
                        elif is_imperative:
                            person = IMPERATIVE_PERSON_LABELS[language].get(person_idx, str(person_idx))
                        else:
                            person = PERSON_LABELS.get(person_idx, str(person_idx))
                        rows.append({
                            "language": language,
                            "verb_infinitive": infinitive,
                            "mood": mood,
                            "tense": tense,
                            "person": person,
                            "form": form,
                        })
    return rows


async def insert_rows(rows: list[dict]) -> None:
    async with AsyncSessionLocal() as session:
        for i in range(0, len(rows), BATCH_SIZE):
            batch = rows[i : i + BATCH_SIZE]
            stmt = pg_insert(VerbConjugation).values(batch).on_conflict_do_nothing()
            await session.execute(stmt)
        await session.commit()


async def main():
    print("Seeding verb conjugations from mlconjug3 data files...")
    total = 0
    for language, lang_code in LANG_CODES.items():
        print(f"  [{language.value}] Building rows...", flush=True)
        rows = build_rows(language, lang_code)
        print(f"  [{language.value}] Inserting {len(rows):,} rows...", flush=True)
        await insert_rows(rows)
        print(f"  [{language.value}] Done.")
        total += len(rows)
    print(f"\nFinished. Total rows: {total:,}")


if __name__ == "__main__":
    asyncio.run(main())
