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

BATCH_SIZE = 1000


def build_rows(language: Language, lang_code: str) -> list[dict]:
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
            for tense, forms in tenses.items():
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
                    for entry in forms:
                        if not isinstance(entry, list) or len(entry) < 2:
                            continue
                        person_idx, suffix = entry[0], entry[1]
                        if suffix is None:
                            continue
                        form = root + suffix
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
