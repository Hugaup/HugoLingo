"""Background stock of ready-made grammar exercises (the grammar twin of sentence_pool).

Each exercise costs two or three LLM calls, plus the attempts the checks reject
(services/grammar.py) — far too slow to make while a user waits. So a few
checked exercises per language are kept in `grammar_pool`, served (and deleted)
by /exercises/generate and topped up in the background. Refills share the
sentence pool's lock and pause while any user waits on a live LLM call, since
Ollama handles one request at a time.
"""
import asyncio
import logging
import random
from collections import defaultdict, deque

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.database import AsyncSessionLocal
from app.models import GrammarPoolItem, Language
from app.services import grammar, sentence_pool
from app.services.grammar import GRAMMAR_PROMPT_VERSION, GrammarItem
from app.services.llm import LLMClient, llm_client

log = logging.getLogger(__name__)

DEFAULT_LEVEL = 2
# Stop a refill after this many rejected attempts in a row (rejections are normal, so it's generous)
MAX_FAILURES_IN_A_ROW = 20

# Levels users recently asked for, so the stock matches what's practised
_recent_levels: dict[Language, deque[int]] = defaultdict(lambda: deque(maxlen=20))
_running: set[Language] = set()
_tasks: set[asyncio.Task] = set()


def note_request(language: Language, level: int) -> None:
    _recent_levels[language].append(level)


async def take(db: AsyncSession, language: Language, level: int) -> GrammarItem | None:
    """Remove and return the stocked exercise closest to `level` (None if the stock is empty).

    Any level beats making the user wait on a live one; note_request steers the
    refill toward the levels being asked for.
    """
    distance = func.abs(GrammarPoolItem.level - level)
    row_id = (await db.execute(
        select(GrammarPoolItem.id)
        .where(GrammarPoolItem.language == language,
               GrammarPoolItem.prompt_version == GRAMMAR_PROMPT_VERSION)
        .order_by(distance, func.random())
        .limit(1)
        .with_for_update(skip_locked=True)
    )).scalar_one_or_none()
    if row_id is None:
        return None
    row = (await db.execute(
        delete(GrammarPoolItem).where(GrammarPoolItem.id == row_id).returning(GrammarPoolItem)
    )).scalar_one()
    await db.commit()
    return GrammarItem(row.sentence_with_error, row.corrected_sentence, row.error_type, row.explanation, row.source)


async def pool_size(db: AsyncSession, language: Language) -> int:
    return await db.scalar(
        select(func.count()).select_from(GrammarPoolItem).where(
            GrammarPoolItem.language == language,
            GrammarPoolItem.prompt_version == GRAMMAR_PROMPT_VERSION,
        )
    ) or 0


def _choose_level(language: Language, rng: random.Random) -> int:
    recent = _recent_levels.get(language)
    return rng.choice(recent) if recent else DEFAULT_LEVEL


async def refill(
    language: Language,
    target: int | None = None,
    session_factory: async_sessionmaker = AsyncSessionLocal,
    client: LLMClient | None = None,
    rng: random.Random | None = None,
    wait_while_busy: bool = True,
) -> int:
    """Make exercises until the stock reaches `target`. Returns how many were added."""
    target = target or settings.grammar_pool_size
    client = client or llm_client
    rng = rng or random.Random()
    added = failures = 0
    async with session_factory() as db:
        # Exercises made by older prompts or checks are never served; clear them out
        await db.execute(delete(GrammarPoolItem).where(
            GrammarPoolItem.language == language,
            GrammarPoolItem.prompt_version != GRAMMAR_PROMPT_VERSION,
        ))
        await db.commit()
        while failures < MAX_FAILURES_IN_A_ROW and await pool_size(db, language) < target:
            while wait_while_busy and sentence_pool.user_waiting():
                await asyncio.sleep(0.5)
            level = _choose_level(language, rng)
            try:
                item, _reason = await grammar.generate_one(db, language, level, client, rng)
            except grammar.LLMUnavailable:
                return added
            if item is None:
                failures += 1
                continue
            failures = 0
            db.add(GrammarPoolItem(
                language=language, level=level, sentence_with_error=item.sentence_with_error,
                corrected_sentence=item.corrected_sentence, error_type=item.error_type,
                explanation=item.explanation, source=item.source, model=client.model,
                prompt_version=GRAMMAR_PROMPT_VERSION,
            ))
            await db.commit()
            added += 1
    return added


def schedule_refill(language: Language) -> None:
    """Top up `language` in the background (no-op if disabled, unsupported or already running)."""
    if not settings.sentence_pool_enabled or not grammar.supports(language) or language in _running:
        return
    task = asyncio.create_task(_run_refill(language))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


async def _run_refill(language: Language) -> None:
    _running.add(language)
    try:
        async with sentence_pool.background_lock:
            added = await refill(language)
        if added:
            log.info("Grammar pool: added %d %s exercises", added, language.value)
    except Exception:
        log.exception("Grammar pool refill failed for %s", language.value)
    finally:
        _running.discard(language)


def start() -> None:
    for language in grammar.LANGUAGES:
        schedule_refill(language)


async def stop() -> None:
    for task in list(_tasks):
        task.cancel()
    await asyncio.gather(*_tasks, return_exceptions=True)
