#!/usr/bin/env python3
"""Load data/vocabulary/{language}.json into vocab_items.

Safe to re-run: rows are upserted by (language, kind, text), so edits to the
JSON (translations, examples, topics) are applied to existing rows.
Run from the backend/ directory:
    source .venv/bin/activate
    python scripts/seed_vocabulary.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import AsyncSessionLocal
from app.services.vocabulary import VOCAB_LANGUAGES, load_entries, upsert_items


async def main() -> None:
    async with AsyncSessionLocal() as db:
        for language in VOCAB_LANGUAGES:
            count = await upsert_items(db, load_entries(language))
            print(f"{language.value}: {count} vocabulary items")


if __name__ == "__main__":
    asyncio.run(main())
