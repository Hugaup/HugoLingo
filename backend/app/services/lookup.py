"""Word lookup for reading: click a word, see what it means, keep it.

Cheapest reliable source first:
  1. the curated vocabulary — also through verb forms (tengo → tener, via
     verb_conjugations), simple plurals (casas → casa) and French elision
     (l'eau → eau);
  2. the word_lookups cache of earlier AI answers;
  3. the LLM, asked for the dictionary form and a short translation in the
     context of the sentence — then cached, so each word costs one call ever.
"""
import json
import re
from datetime import datetime, timezone

import httpx
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Language, VerbConjugation, VocabItem, VocabReview, WordLookup
from app.services import sentence_pool
from app.services.exercise_gen import LANGUAGE_NAMES
from app.services.llm import LLMClient, llm_client

_WORD = re.compile(r"[^\W\d_]+(?:['’-][^\W\d_]+)*")


class LookupFailed(Exception):
    """The LLM gave no usable answer."""


def clean_word(raw: str) -> str:
    """The first word in `raw`, lowercased, curly apostrophes straightened ('' if none)."""
    match = _WORD.search(raw.replace("’", "'"))
    return match.group(0).lower() if match else ""


def _candidates(word: str) -> list[str]:
    forms = [word]
    if "'" in word:
        forms.append(word.split("'", 1)[1])  # French elision: l'eau → eau, j'aime → aime
    for suffix in ("es", "s"):
        if word.endswith(suffix) and len(word) > len(suffix) + 2:
            forms.append(word[: -len(suffix)])
    return forms


async def find_curated(db: AsyncSession, language: Language, word: str) -> VocabItem | None:
    """The shared vocabulary item for a word as it appears in a text, if there is one."""
    candidates = _candidates(word)
    infinitives = (await db.execute(
        select(VerbConjugation.verb_infinitive).distinct().where(
            VerbConjugation.language == language,
            func.lower(VerbConjugation.form).in_(candidates),
        ).limit(5)
    )).scalars().all()
    candidates += [i.lower() for i in infinitives]

    items = (await db.execute(
        select(VocabItem).where(
            VocabItem.language == language,
            VocabItem.owner_id.is_(None),
            func.lower(VocabItem.text).in_(candidates),
        )
    )).scalars().all()
    by_text = {i.text.lower(): i for i in items}
    return next((by_text[c] for c in candidates if c in by_text), None)


# Spanish nouns that end like a plural but are singular
_SPANISH_SINGULAR_ES = {"lunes", "martes", "miércoles", "jueves", "viernes"}


def singular_guess(language: Language, word: str) -> str:
    """Rule-of-thumb singular for a Spanish plural noun/adjective: the local
    LLM often returns Spanish plurals unchanged as their "dictionary form".
    (It singularises French fine, and French has many singular nouns ending
    in -s — pays, temps, fois — so French is left alone.)"""
    if language != Language.spanish or len(word) < 4 or word in _SPANISH_SINGULAR_ES:
        return word
    if word.endswith("ces"):  # luces → luz, veces → vez
        return word[:-3] + "z"
    # Only these consonants can end a Spanish word, so only then was "-es" added
    if word.endswith("es") and word[-3] in "dlnrsjyx":  # ciudades → ciudad, canciones → canción
        stem = word[:-2]
        return stem[:-3] + "ión" if stem.endswith("ion") else stem
    if word[-2:] in ("as", "os", "es"):  # bicicletas → bicicleta, chicos → chico, coches → coche
        return word[:-1]
    return word  # crisis, virus… are singular


def _messages(language: Language, word: str, context: str) -> list[dict]:
    lang = LANGUAGE_NAMES[language]
    return [
        {"role": "system", "content": f"You are a {lang}–English dictionary. Respond with valid JSON only."},
        {"role": "user", "content": (
            f'In the {lang} sentence "{context}", what does the word "{word}" mean? '
            'Return JSON with exactly these keys: '
            f'"lemma" (its dictionary form: the {lang} infinitive for verbs, the masculine singular for nouns '
            'and adjectives — e.g. "casas" → "casa", "corrió" → "correr", "rojas" → "rojo", "chevaux" → "cheval"), '
            '"translation" (its English meaning here, 1 to 4 words), '
            '"pos" (one of: noun, verb, adjective, adverb, other).'
        )},
    ]


async def lookup(
    db: AsyncSession, language: Language, raw_word: str, context: str, client: LLMClient | None = None,
) -> dict:
    word = clean_word(raw_word)
    if not word:
        raise LookupFailed("not a word")

    item = await find_curated(db, language, word)
    if item:
        return {"word": word, "lemma": item.text, "translation": item.translation, "pos": item.pos,
                "source": "vocabulary", "item_id": item.id}

    cached = (await db.execute(
        select(WordLookup).where(WordLookup.language == language, WordLookup.word == word)
    )).scalar_one_or_none()
    if cached:
        return {"word": word, "lemma": cached.lemma, "translation": cached.translation, "pos": cached.pos,
                "source": "dictionary", "item_id": None}

    client = client or llm_client
    try:
        with sentence_pool.live_request():
            data = await client.chat_json(_messages(language, word, context[:400]), max_tokens=80)
    except (json.JSONDecodeError, KeyError, httpx.HTTPStatusError, httpx.RequestError) as e:
        raise LookupFailed(str(e)) from e
    translation = str(data.get("translation", "")).strip() if isinstance(data, dict) else ""
    if not translation:
        raise LookupFailed("no translation")
    lemma = (clean_word(str(data.get("lemma", ""))) or word)[:128]
    pos = str(data.get("pos", "")).strip().lower()[:16] or None
    if lemma == word and pos in ("noun", "adjective"):
        lemma = singular_guess(language, word)

    db.add(WordLookup(language=language, word=word, lemma=lemma, translation=translation[:256], pos=pos))
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()  # someone looked the same word up at the same moment; fine
    return {"word": word, "lemma": lemma, "translation": translation, "pos": pos, "source": "ai", "item_id": None}


# ── The user's own word list ─────────────────────────────────────────────────

async def personal_item(db: AsyncSession, user_id: int, language: Language, text: str) -> VocabItem | None:
    return (await db.execute(
        select(VocabItem).where(
            VocabItem.owner_id == user_id, VocabItem.language == language, func.lower(VocabItem.text) == text.lower(),
        )
    )).scalar_one_or_none()


async def is_saved(db: AsyncSession, user_id: int, item_id: int | None, language: Language, lemma: str) -> bool:
    """Whether the word is already in the user's reviews (curated) or own list (personal)."""
    if item_id is not None:
        return await db.scalar(
            select(func.count()).select_from(VocabReview)
            .where(VocabReview.user_id == user_id, VocabReview.item_id == item_id)
        ) > 0
    return await personal_item(db, user_id, language, lemma) is not None


async def add_to_my_words(
    db: AsyncSession, user_id: int, language: Language, lemma: str, translation: str,
    pos: str | None, example: str,
) -> tuple[VocabItem, bool]:
    """Start learning a word: a curated item gets a review due now; any other word
    becomes a personal item (topic "my_words"). Returns (item, newly_added). Commits."""
    now = datetime.now(timezone.utc)
    item = await find_curated(db, language, lemma.lower()) or await personal_item(db, user_id, language, lemma)
    if item is None:
        item = VocabItem(
            language=language, kind="personal", text=lemma, article=None, translation=translation,
            pos=pos, topic="my_words", level=1, frequency_rank=None,
            example=example or lemma, example_translation="", owner_id=user_id,
        )
        db.add(item)
        await db.flush()

    review = (await db.execute(
        select(VocabReview).where(VocabReview.user_id == user_id, VocabReview.item_id == item.id)
    )).scalar_one_or_none()
    added = review is None
    if added:
        db.add(VocabReview(user_id=user_id, item_id=item.id, box=0, due_at=now, last_seen_at=now,
                           correct_count=0, wrong_count=0))
    await db.commit()
    return item, added
