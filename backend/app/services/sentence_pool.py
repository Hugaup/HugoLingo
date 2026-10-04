"""Background stock of ready-made practice sentences.

Generating one sentence with the local LLM takes a second or more, plus retries
when its output is rejected. This keeps a stock of already-validated sentences
per language in `sentence_pool`, so /conjugation-exercises/sentence/generate can
usually answer instantly. Served rows are deleted (never shown twice) and the
stock is topped up in the background — but only while no user is waiting on a
live LLM call, since Ollama handles one request at a time.
"""
import asyncio
import logging
import random
from collections import defaultdict, deque
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.database import AsyncSessionLocal
from app.models import Language, SentencePoolItem
from app.schemas import SentenceExerciseItem, TenseFilter
from app.services.conjugation_utils import canonical_tense
from app.services.llm import LLMClient, llm_client
from app.services.sentences import COMMON_TENSES, SENTENCE_PROMPT_VERSION, NoConjugationData, generate_one

log = logging.getLogger(__name__)

POOL_LANGUAGES = [Language.spanish, Language.french, Language.english]
# Stop a refill after this many rejected/failed generations in a row (e.g. Ollama down)
MAX_FAILURES_IN_A_ROW = 10

# Tense selections users recently asked for, so the stock matches what's practised
_recent_requests: dict[Language, deque[tuple[TenseFilter, ...]]] = defaultdict(lambda: deque(maxlen=20))
_live_requests = 0
_running: set[Language] = set()
_tasks: set[asyncio.Task] = set()
# One background refill talks to the LLM at a time
background_lock = asyncio.Lock()


@contextmanager
def live_request() -> Iterator[None]:
    """Mark a user waiting on a live LLM call; background refills pause meanwhile."""
    global _live_requests
    _live_requests += 1
    try:
        yield
    finally:
        _live_requests -= 1


def user_waiting() -> bool:
    """True while some user waits on a live LLM call (background work should hold off)."""
    return _live_requests > 0


def note_request(language: Language, tenses: list[TenseFilter]) -> None:
    _recent_requests[language].append(tuple(tenses))


def _tense_condition(tenses: list[TenseFilter]):
    return or_(*[
        and_(
            func.lower(SentencePoolItem.mood) == t.mood.lower(),
            func.lower(SentencePoolItem.tense) == canonical_tense(t.tense).lower(),
        )
        for t in tenses
    ])


async def take(db: AsyncSession, language: Language, tenses: list[TenseFilter], count: int) -> list[SentenceExerciseItem]:
    """Remove and return up to `count` stocked sentences matching `tenses` (any tense if empty)."""
    query = select(SentencePoolItem.id).where(
        SentencePoolItem.language == language,
        SentencePoolItem.prompt_version == SENTENCE_PROMPT_VERSION,
    )
    if tenses:
        query = query.where(_tense_condition(tenses))
    ids = (await db.execute(
        query.order_by(func.random()).limit(count).with_for_update(skip_locked=True)
    )).scalars().all()
    if not ids:
        return []
    rows = (await db.execute(
        delete(SentencePoolItem).where(SentencePoolItem.id.in_(ids)).returning(SentencePoolItem)
    )).scalars().all()
    await db.commit()
    return [
        SentenceExerciseItem(
            sentence=r.sentence, subject_hint=r.subject_hint, verb_infinitive=r.verb_infinitive,
            mood=r.mood, tense=r.tense, person=r.person, correct_form=r.correct_form, alternates=r.alternates,
        )
        for r in rows
    ]


async def pool_size(db: AsyncSession, language: Language) -> int:
    return await db.scalar(
        select(func.count()).select_from(SentencePoolItem).where(
            SentencePoolItem.language == language,
            SentencePoolItem.prompt_version == SENTENCE_PROMPT_VERSION,
        )
    ) or 0


def _choose_tenses(language: Language, rng: random.Random) -> list[TenseFilter]:
    """Mostly what users recently asked for; otherwise the everyday tenses."""
    recent = _recent_requests.get(language)
    if recent and rng.random() < 0.7:
        choice = list(rng.choice(recent))
        if choice:
            return choice
    return [TenseFilter(mood=m, tense=t) for m, t in COMMON_TENSES.get(language, [])]


async def refill(
    language: Language,
    target: int | None = None,
    session_factory: async_sessionmaker = AsyncSessionLocal,
    client: LLMClient | None = None,
    rng: random.Random | None = None,
    wait_while_busy: bool = True,
    judge: bool | None = None,
) -> int:
    """Generate sentences until the stock reaches `target`. Returns how many were added."""
    target = target or settings.sentence_pool_size
    judge = settings.sentence_judge if judge is None else judge
    client = client or llm_client
    rng = rng or random.Random()
    added = failures = 0
    async with session_factory() as db:
        # Sentences made by an older prompt are never served; clear them out
        await db.execute(delete(SentencePoolItem).where(
            SentencePoolItem.language == language,
            SentencePoolItem.prompt_version != SENTENCE_PROMPT_VERSION,
        ))
        await db.commit()
        while failures < MAX_FAILURES_IN_A_ROW and await pool_size(db, language) < target:
            while wait_while_busy and user_waiting():
                await asyncio.sleep(0.5)
            try:
                item = await generate_one(db, language, _choose_tenses(language, rng), client, judge=judge)
            except NoConjugationData:
                return added  # no verb data for this language/tense mix
            if item is None:
                failures += 1
                continue
            failures = 0
            db.add(SentencePoolItem(
                language=language, model=client.model, prompt_version=SENTENCE_PROMPT_VERSION, **item.model_dump(),
            ))
            await db.commit()
            added += 1
    return added


def schedule_refill(language: Language) -> None:
    """Top up `language` in the background (no-op if disabled or already running)."""
    if not settings.sentence_pool_enabled or language in _running:
        return
    task = asyncio.create_task(_run_refill(language))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


async def _run_refill(language: Language) -> None:
    _running.add(language)
    try:
        async with background_lock:
            added = await refill(language)
        if added:
            log.info("Sentence pool: added %d %s sentences", added, language.value)
    except Exception:
        log.exception("Sentence pool refill failed for %s", language.value)
    finally:
        _running.discard(language)


def start() -> None:
    for language in POOL_LANGUAGES:
        schedule_refill(language)


async def stop() -> None:
    for task in list(_tasks):
        task.cancel()
    await asyncio.gather(*_tasks, return_exceptions=True)
