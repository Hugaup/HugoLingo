"""Answer history: recording attempts, spaced-review scheduling, weak-spot scoring.

Every conjugation answer from any practice area goes through record_attempts(),
which appends to `attempts` and updates the per-verb+tense Leitner box in
`review_items`. Weak spots are computed on the fly from recent attempts with
exponential decay, so old mistakes fade and fixed ones stop being flagged.
"""
import random
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Hashable, Iterable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import Integer, cast, func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Attempt, Language, ReviewItem, VerbConjugation
from app.services.conjugation_utils import canonical_tense, variant_tense_names

# Leitner boxes: a wrong answer sends an item back to box 0 (due straight away);
# each right answer moves it up a box and pushes its next review further out.
REVIEW_INTERVALS = [
    timedelta(0),
    timedelta(days=1),
    timedelta(days=3),
    timedelta(days=7),
    timedelta(days=14),
    timedelta(days=30),
]
MAX_BOX = len(REVIEW_INTERVALS) - 1

# An answer's weight halves every HALF_LIFE_DAYS, so last week's mistakes count
# for much more than last quarter's. Beyond HISTORY_WINDOW the weight is < 0.3%.
HALF_LIFE_DAYS = 14
HISTORY_WINDOW = timedelta(days=120)
# Pseudo-answers added to the denominator: a single slip ranks below a pattern
SMOOTHING = 2.0
# Below this score an item isn't worth flagging (e.g. 1 old mistake, many rights)
MIN_WEAKNESS = 0.1

PERSON_ORDER = ["1s", "2s", "3s", "1p", "2p", "3p"]


@dataclass
class AttemptIn:
    verb_infinitive: str
    mood: str | None
    tense: str | None
    person: str | None
    user_answer: str
    expected: str
    is_correct: bool
    is_almost: bool = False


# ── Pure helpers ─────────────────────────────────────────────────────────────

def next_review(box: int, correct: bool, now: datetime) -> tuple[int, datetime]:
    new_box = min(box + 1, MAX_BOX) if correct else 0
    return new_box, now + REVIEW_INTERVALS[new_box]


def answer_weight(age: timedelta) -> float:
    return 0.5 ** (max(age.total_seconds(), 0.0) / 86400 / HALF_LIFE_DAYS)


def score_groups(
    rows: Iterable[tuple[Hashable, bool, datetime]],
    now: datetime,
) -> list[dict]:
    """Rank groups of answers by recency-weighted error rate.

    rows: (group key, is_correct, answered_at). Returns the groups scoring at
    least MIN_WEAKNESS, weakest first, as dicts with key/attempts/mistakes/
    weakness/last_mistake_at.
    """
    groups: dict[Hashable, dict] = {}
    for key, is_correct, answered_at in rows:
        g = groups.setdefault(key, {
            "key": key, "attempts": 0, "mistakes": 0,
            "w_total": 0.0, "w_wrong": 0.0, "last_mistake_at": None,
        })
        w = answer_weight(now - answered_at)
        g["attempts"] += 1
        g["w_total"] += w
        if not is_correct:
            g["mistakes"] += 1
            g["w_wrong"] += w
            if g["last_mistake_at"] is None or answered_at > g["last_mistake_at"]:
                g["last_mistake_at"] = answered_at

    ranked = []
    for g in groups.values():
        weakness = g.pop("w_wrong") / (g.pop("w_total") + SMOOTHING)
        if weakness >= MIN_WEAKNESS:
            ranked.append({**g, "weakness": round(weakness, 3)})
    ranked.sort(key=lambda g: (-g["weakness"], -g["mistakes"]))
    return ranked


def current_streak(active_days: set[date], today: date) -> int:
    """Consecutive days with practice, ending today — or yesterday, since a
    streak isn't broken until a whole day passes without practice."""
    day = today if today in active_days else today - timedelta(days=1)
    streak = 0
    while day in active_days:
        streak += 1
        day -= timedelta(days=1)
    return streak


def resolve_timezone(name: str) -> str:
    try:
        ZoneInfo(name)
        return name
    except (ZoneInfoNotFoundError, ValueError):
        return "UTC"


# ── Recording ────────────────────────────────────────────────────────────────

async def record_attempts(
    db: AsyncSession,
    user_id: int,
    language: Language,
    source: str,
    attempts: list[AttemptIn],
    now: datetime | None = None,
) -> None:
    """Store answers and update review boxes. Commits."""
    if not attempts:
        return
    now = now or datetime.now(timezone.utc)

    # A batch (e.g. a whole verb table) moves each verb+tense's box once:
    # up if every answer for it was right, back to 0 if any was wrong.
    outcomes: dict[tuple[str, str, str], bool] = {}
    for a in attempts:
        tense = canonical_tense(a.tense) if a.tense else None
        db.add(Attempt(
            user_id=user_id, language=language, source=source,
            verb_infinitive=a.verb_infinitive, mood=a.mood, tense=tense, person=a.person,
            user_answer=a.user_answer[:512], expected=a.expected[:512],
            is_correct=a.is_correct, is_almost=a.is_almost and not a.is_correct, created_at=now,
        ))
        if a.mood and tense:
            key = (a.verb_infinitive, a.mood, tense)
            outcomes[key] = outcomes.get(key, True) and a.is_correct

    if outcomes:
        existing = {
            (r.verb_infinitive, r.mood, r.tense): r
            for r in (await db.execute(
                select(ReviewItem).where(
                    ReviewItem.user_id == user_id,
                    ReviewItem.language == language,
                    tuple_(ReviewItem.verb_infinitive, ReviewItem.mood, ReviewItem.tense).in_(list(outcomes)),
                )
            )).scalars()
        }
        for key, correct in outcomes.items():
            item = existing.get(key)
            if item is None:
                item = ReviewItem(
                    user_id=user_id, language=language,
                    verb_infinitive=key[0], mood=key[1], tense=key[2],
                    box=0, correct_count=0, wrong_count=0,
                )
                db.add(item)
            item.box, item.due_at = next_review(item.box, correct, now)
            item.last_seen_at = now
            if correct:
                item.correct_count += 1
            else:
                item.wrong_count += 1

    await db.commit()


# ── Queries ──────────────────────────────────────────────────────────────────

async def weak_spots(db: AsyncSession, user_id: int, language: Language, limit: int, now: datetime) -> dict:
    rows = (await db.execute(
        select(Attempt.verb_infinitive, Attempt.mood, Attempt.tense, Attempt.is_correct, Attempt.created_at)
        .where(
            Attempt.user_id == user_id,
            Attempt.language == language,
            Attempt.created_at >= now - HISTORY_WINDOW,
        )
    )).all()

    def as_items(groups: list[dict], fields: tuple[str, ...]) -> list[dict]:
        return [
            {**dict(zip(fields, g["key"])), **{k: v for k, v in g.items() if k != "key"}}
            for g in groups[:limit]
        ]

    tensed = [r for r in rows if r.mood and r.tense]
    due_count = await db.scalar(
        select(func.count()).select_from(ReviewItem).where(
            ReviewItem.user_id == user_id, ReviewItem.language == language, ReviewItem.due_at <= now,
        )
    )
    return {
        "verbs": as_items(
            score_groups([((r.verb_infinitive,), r.is_correct, r.created_at) for r in rows], now),
            ("verb_infinitive",),
        ),
        "tenses": as_items(
            score_groups([((r.mood, r.tense), r.is_correct, r.created_at) for r in tensed], now),
            ("mood", "tense"),
        ),
        "combos": as_items(
            score_groups([((r.verb_infinitive, r.mood, r.tense), r.is_correct, r.created_at) for r in tensed], now),
            ("verb_infinitive", "mood", "tense"),
        ),
        "due_count": due_count or 0,
    }


async def drill_prompts(
    db: AsyncSession,
    user_id: int,
    language: Language,
    count: int,
    now: datetime,
    rng: random.Random | None = None,
) -> list[dict]:
    """Prompts for a focused review: due review items first, then weak spots.

    Each verb+tense gets several persons when there are fewer items than
    `count`; persons the user recently got wrong come first.
    """
    rng = rng or random.Random()

    due = (await db.execute(
        select(ReviewItem.verb_infinitive, ReviewItem.mood, ReviewItem.tense)
        .where(ReviewItem.user_id == user_id, ReviewItem.language == language, ReviewItem.due_at <= now)
        .order_by(ReviewItem.box, ReviewItem.due_at)
        .limit(count)
    )).all()
    combos: dict[tuple[str, str, str], str] = {tuple(r): "due" for r in due}
    for item in (await weak_spots(db, user_id, language, count, now))["combos"]:
        if len(combos) >= count:
            break
        combos.setdefault((item["verb_infinitive"], item["mood"], item["tense"]), "weak")

    queues: list[tuple[tuple[str, str, str], str, list[str]]] = []
    for (verb, mood, tense), reason in combos.items():
        available = set((await db.execute(
            select(VerbConjugation.person).distinct().where(
                VerbConjugation.language == language,
                VerbConjugation.verb_infinitive == verb,
                VerbConjugation.mood == mood,
                VerbConjugation.tense.in_(variant_tense_names(tense)),
            )
        )).scalars())
        if not available:
            continue
        missed = (await db.execute(
            select(Attempt.person)
            .where(
                Attempt.user_id == user_id, Attempt.language == language,
                Attempt.verb_infinitive == verb, Attempt.mood == mood, Attempt.tense == tense,
                Attempt.is_correct.is_(False), Attempt.person.is_not(None),
            )
            .order_by(Attempt.created_at.desc())
        )).scalars()
        order = list(dict.fromkeys(p for p in missed if p in available))
        rest = [p for p in PERSON_ORDER if p in available and p not in order]
        rest += sorted(p for p in available if p not in PERSON_ORDER and p not in order)
        rng.shuffle(rest)
        queues.append(((verb, mood, tense), reason, order + rest))

    # Round-robin across verb+tenses so the drill mixes them up
    prompts: list[dict] = []
    while len(prompts) < count and any(q for _, _, q in queues):
        for (verb, mood, tense), reason, persons in queues:
            if persons and len(prompts) < count:
                prompts.append({
                    "verb_infinitive": verb, "mood": mood, "tense": tense,
                    "person": persons.pop(0), "reason": reason,
                })
    return prompts


async def stats(
    db: AsyncSession,
    user_id: int,
    language: Language | None,
    tz: str,
    days: int,
    now: datetime,
) -> dict:
    """Totals and daily activity (for `language`, or all), plus today's count and
    the streak (always across all languages), with days in the user's timezone."""
    tz = resolve_timezone(tz)
    today = now.astimezone(ZoneInfo(tz)).date()
    local_day = func.date(func.timezone(tz, Attempt.created_at))

    lang_filter = [Attempt.language == language] if language else []
    total, correct = (await db.execute(
        select(func.count(), func.coalesce(func.sum(cast(Attempt.is_correct, Integer)), 0))
        .where(Attempt.user_id == user_id, *lang_filter)
    )).one()

    start = today - timedelta(days=days - 1)
    per_day = {
        d: (t, c) for d, t, c in (await db.execute(
            select(local_day, func.count(), func.sum(cast(Attempt.is_correct, Integer)))
            .where(Attempt.user_id == user_id, local_day >= start, *lang_filter)
            .group_by(local_day)
        )).all()
    }
    daily = []
    for i in range(days):
        d = start + timedelta(days=i)
        t, c = per_day.get(d, (0, 0))
        daily.append({"date": d, "total": t, "correct": c})

    active_days = set((await db.execute(
        select(local_day).distinct().where(Attempt.user_id == user_id)
    )).scalars())
    today_count = await db.scalar(
        select(func.count()).select_from(Attempt).where(Attempt.user_id == user_id, local_day == today)
    )

    return {
        "total": total,
        "correct": correct,
        "accuracy": round(correct / total * 100, 1) if total else 0.0,
        "today_count": today_count or 0,
        "streak_days": current_streak(active_days, today),
        "daily": daily,
    }


async def grid(db: AsyncSession, user_id: int, language: Language, max_verbs: int) -> dict:
    """Accuracy per verb × tense for the user's most-practised verbs."""
    rows = (await db.execute(
        select(
            Attempt.verb_infinitive, Attempt.mood, Attempt.tense,
            func.count(), func.sum(cast(Attempt.is_correct, Integer)),
        )
        .where(Attempt.user_id == user_id, Attempt.language == language, Attempt.mood.is_not(None))
        .group_by(Attempt.verb_infinitive, Attempt.mood, Attempt.tense)
    )).all()

    per_verb: dict[str, dict] = {}
    for verb, mood, tense, n, ok in rows:
        entry = per_verb.setdefault(verb, {"verb_infinitive": verb, "total": 0, "cells": {}})
        entry["total"] += n
        entry["cells"][f"{mood}||{tense}"] = {"attempts": n, "correct": ok}

    top = sorted(per_verb.values(), key=lambda v: (-v["total"], v["verb_infinitive"]))[:max_verbs]
    tenses = sorted({tuple(k.split("||", 1)) for v in top for k in v["cells"]})
    return {
        "tenses": [{"mood": m, "tense": t} for m, t in tenses],
        "rows": [{"verb_infinitive": v["verb_infinitive"], "cells": v["cells"]} for v in top],
    }
