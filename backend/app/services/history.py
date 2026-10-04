"""Answer history: recording attempts, spaced-review scheduling, weak spots.

Every conjugation answer from any practice area goes through record_attempts(),
which appends to `attempts` and updates the per-verb+tense Leitner box in
`review_items`. Anything you've got wrong has a status read off its box —
needs work → getting there → fixed — and "Work on this" lists the first two.
Recent attempts, weighted by age, only decide the order within "needs work".
"""
from collections import Counter
import random
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Hashable, Iterable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import Integer, cast, func, select, tuple_, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Attempt, ConversationTurn, GrammarAttempt, Language, ReviewItem, VerbConjugation, VocabAttempt, VocabItem, VocabReview
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
# A box only moves up when its check-up is due: getting a form right again a
# minute after seeing the answer proves nothing. "Due" starts this long before
# due_at, so a check-up "tomorrow" is open all of tomorrow, not just after the
# exact time of today's answer.
DUE_SLACK = timedelta(hours=8)
# Something you got wrong is fixed once it has passed the 1-day and the 3-day
# check-ups (box 1 → 2 → 3); before that it's "getting there".
FIXED_BOX = 3

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

def is_due(due_at: datetime | None, now: datetime) -> bool:
    return due_at is None or due_at <= now + DUE_SLACK


def next_review(box: int, due_at: datetime | None, correct: bool, now: datetime) -> tuple[int, datetime]:
    """Wrong → box 0, due now. Right → up a box, but only if it was due;
    a right answer before the check-up leaves the schedule alone."""
    if not correct:
        return 0, now
    if not is_due(due_at, now):
        return box, due_at
    new_box = min(box + 1, MAX_BOX)
    return new_box, now + REVIEW_INTERVALS[new_box]


def review_status(box: int, wrong_count: int) -> str | None:
    """needs_work | getting_there | fixed; None for something never got wrong."""
    if not wrong_count:
        return None
    if box == 0:
        return "needs_work"
    return "getting_there" if box < FIXED_BOX else "fixed"


def answer_weight(age: timedelta) -> float:
    return 0.5 ** (max(age.total_seconds(), 0.0) / 86400 / HALF_LIFE_DAYS)


def score_groups(
    rows: Iterable[tuple[Hashable, bool, datetime]],
    now: datetime,
    min_weakness: float = MIN_WEAKNESS,
) -> list[dict]:
    """Rank groups of answers by recency-weighted error rate.

    rows: (group key, is_correct, answered_at). Returns the groups scoring at
    least min_weakness, weakest first, as dicts with key/attempts/mistakes/
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
        if weakness >= min_weakness:
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
) -> dict[tuple[str, str, str], dict]:
    """Store answers and update review boxes. Commits.

    Returns each verb+tense's review state after the answers:
    {(verb, mood, tense): {"status", "due_at"}}.
    """
    if not attempts:
        return {}
    now = now or datetime.now(timezone.utc)

    # A batch (e.g. a whole verb table) moves each verb+tense's box once:
    # up if every answer for it was right (and it was due), back to 0 if any was wrong.
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

    states: dict[tuple[str, str, str], dict] = {}
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
            item.box, item.due_at = next_review(item.box, item.due_at, correct, now)
            item.last_seen_at = now
            if correct:
                item.correct_count += 1
            else:
                item.wrong_count += 1
            states[key] = {"status": review_status(item.box, item.wrong_count), "due_at": item.due_at}

    await db.commit()
    return states


# ── Queries ──────────────────────────────────────────────────────────────────

async def weak_spots(db: AsyncSession, user_id: int, language: Language, limit: int, now: datetime) -> dict:
    """What "Work on this" shows: verb+tenses that need work (worst first), then
    the ones getting there (check-up due first), plus counts per status."""
    mistaken = list((await db.execute(
        select(ReviewItem).where(
            ReviewItem.user_id == user_id, ReviewItem.language == language, ReviewItem.wrong_count > 0,
        )
    )).scalars())
    statuses = {r.id: review_status(r.box, r.wrong_count) for r in mistaken}
    mistakes = await mistake_counts(db, user_id, language)

    rows = (await db.execute(
        select(Attempt.verb_infinitive, Attempt.mood, Attempt.tense, Attempt.is_correct, Attempt.created_at)
        .where(
            Attempt.user_id == user_id,
            Attempt.language == language,
            Attempt.created_at >= now - HISTORY_WINDOW,
            Attempt.mood.is_not(None),
            Attempt.tense.is_not(None),
        )
    )).all()
    weakness = {
        g["key"]: g["weakness"]
        for g in score_groups([((r.verb_infinitive, r.mood, r.tense), r.is_correct, r.created_at) for r in rows],
                              now, min_weakness=0)
    }

    def key(r: ReviewItem) -> tuple[str, str, str]:
        return (r.verb_infinitive, r.mood, r.tense)

    needs_work = sorted(
        (r for r in mistaken if statuses[r.id] == "needs_work"),
        key=lambda r: (-weakness.get(key(r), 0), -mistakes.get(key(r), (0, None))[0]),
    )
    getting_there = sorted((r for r in mistaken if statuses[r.id] == "getting_there"), key=lambda r: r.due_at)
    upcoming = [r.due_at for r in getting_there if not is_due(r.due_at, now)]

    due_count = await db.scalar(
        select(func.count()).select_from(ReviewItem).where(
            ReviewItem.user_id == user_id, ReviewItem.language == language,
            ReviewItem.due_at <= now + DUE_SLACK,
        )
    )
    counts = Counter(statuses.values())
    return {
        "items": [
            {
                "verb_infinitive": r.verb_infinitive, "mood": r.mood, "tense": r.tense,
                "status": statuses[r.id], "due_at": r.due_at, "is_due": is_due(r.due_at, now),
                "mistakes": mistakes.get(key(r), (0, None))[0],
                "last_mistake_at": mistakes.get(key(r), (0, None))[1],
            }
            for r in (needs_work + getting_there)[:limit]
        ],
        "counts": {s: counts.get(s, 0) for s in ("needs_work", "getting_there", "fixed")},
        "due_count": due_count or 0,
        "next_check_up_at": min(upcoming, default=None),
    }


async def mistake_counts(
    db: AsyncSession, user_id: int, language: Language,
) -> dict[tuple[str, str, str], tuple[int, datetime]]:
    """(verb, mood, tense) → (wrong answers ever, the latest one's time)."""
    rows = (await db.execute(
        select(Attempt.verb_infinitive, Attempt.mood, Attempt.tense, func.count(), func.max(Attempt.created_at))
        .where(
            Attempt.user_id == user_id, Attempt.language == language,
            Attempt.is_correct.is_(False), Attempt.mood.is_not(None), Attempt.tense.is_not(None),
        )
        .group_by(Attempt.verb_infinitive, Attempt.mood, Attempt.tense)
    )).all()
    return {(v, m, t): (n, last) for v, m, t, n, last in rows}


STATUS_ORDER = {"needs_work": 0, "getting_there": 1, "fixed": 2}
MISTAKES_SHOWN = 5


async def mistake_history(db: AsyncSession, user_id: int, language: Language, now: datetime) -> dict:
    """Everything you've ever got wrong in a language — verb+tenses and words —
    with each one's status and its latest wrong answers."""
    reviews = list((await db.execute(
        select(ReviewItem).where(
            ReviewItem.user_id == user_id, ReviewItem.language == language, ReviewItem.wrong_count > 0,
        )
    )).scalars())
    wrong = (await db.execute(
        select(Attempt).where(
            Attempt.user_id == user_id, Attempt.language == language,
            Attempt.is_correct.is_(False), Attempt.mood.is_not(None), Attempt.tense.is_not(None),
        ).order_by(Attempt.created_at.desc())
    )).scalars()
    by_combo: dict[tuple[str, str, str], list[Attempt]] = {}
    for a in wrong:
        by_combo.setdefault((a.verb_infinitive, a.mood, a.tense), []).append(a)

    verbs = []
    for r in reviews:
        answers = by_combo.get((r.verb_infinitive, r.mood, r.tense), [])
        verbs.append({
            "verb_infinitive": r.verb_infinitive, "mood": r.mood, "tense": r.tense,
            "status": review_status(r.box, r.wrong_count), "due_at": r.due_at, "is_due": is_due(r.due_at, now),
            "last_seen_at": r.last_seen_at, "total_mistakes": len(answers),
            "mistakes": [
                {"person": a.person, "user_answer": a.user_answer, "expected": a.expected,
                 "is_almost": a.is_almost, "source": a.source, "created_at": a.created_at}
                for a in answers[:MISTAKES_SHOWN]
            ],
            "last_mistake_at": answers[0].created_at if answers else None,
        })

    word_reviews = (await db.execute(
        select(VocabReview, VocabItem)
        .join(VocabItem, VocabItem.id == VocabReview.item_id)
        .where(VocabReview.user_id == user_id, VocabItem.language == language, VocabReview.wrong_count > 0)
    )).all()
    word_wrong: dict[int, list[VocabAttempt]] = {}
    if word_reviews:
        for a in (await db.execute(
            select(VocabAttempt).where(
                VocabAttempt.user_id == user_id, VocabAttempt.is_correct.is_(False),
                VocabAttempt.item_id.in_([item.id for _, item in word_reviews]),
            ).order_by(VocabAttempt.created_at.desc())
        )).scalars():
            word_wrong.setdefault(a.item_id, []).append(a)

    words = []
    for review, item in word_reviews:
        answers = word_wrong.get(item.id, [])
        words.append({
            "item_id": item.id, "text": f"{item.article} {item.text}" if item.article else item.text,
            "translation": item.translation,
            "status": review_status(review.box, review.wrong_count), "due_at": review.due_at,
            "is_due": is_due(review.due_at, now), "last_seen_at": review.last_seen_at,
            "total_mistakes": len(answers),
            "mistakes": [
                {"user_answer": a.user_answer, "exercise": a.exercise, "is_almost": a.is_almost, "created_at": a.created_at}
                for a in answers[:MISTAKES_SHOWN]
            ],
            "last_mistake_at": answers[0].created_at if answers else None,
        })

    def order(g: dict):
        last = g["last_mistake_at"] or g["last_seen_at"]
        return (STATUS_ORDER[g["status"]], -last.timestamp())

    verbs.sort(key=order)
    words.sort(key=order)
    statuses = Counter(g["status"] for g in verbs + words)
    return {
        "verbs": verbs,
        "words": words,
        "counts": {s: statuses.get(s, 0) for s in STATUS_ORDER},
    }


async def drill_prompts(
    db: AsyncSession,
    user_id: int,
    language: Language,
    count: int,
    now: datetime,
    rng: random.Random | None = None,
    only: tuple[str, str, str] | None = None,
) -> list[dict]:
    """Prompts for a focused review: whatever is due — things that need work,
    then check-ups — or, with `only`, every person of that one verb+tense.

    Each verb+tense gets several persons when there are fewer items than
    `count`; persons the user recently got wrong come first.
    """
    rng = rng or random.Random()

    if only:
        combos: dict[tuple[str, str, str], str] = {only: "practice"}
    else:
        due = (await db.execute(
            select(ReviewItem.verb_infinitive, ReviewItem.mood, ReviewItem.tense, ReviewItem.box)
            .where(
                ReviewItem.user_id == user_id, ReviewItem.language == language,
                ReviewItem.due_at <= now + DUE_SLACK,
            )
            .order_by(ReviewItem.box, ReviewItem.due_at)
            .limit(count)
        )).all()
        combos = {(v, m, t): "needs_work" if box == 0 else "check_up" for v, m, t, box in due}

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
    the streak (always across all languages), with days in the user's timezone.
    Counts every answer: conjugation, vocabulary and grammar attempts and conversation
    messages alike. (A conversation's verb mistakes are also stored as attempts for
    the weak spots; they're left out here so the message isn't counted twice.)"""
    tz = resolve_timezone(tz)
    today = now.astimezone(ZoneInfo(tz)).date()
    answers = union_all(
        select(Attempt.created_at, Attempt.is_correct, Attempt.language)
        .where(Attempt.user_id == user_id, Attempt.source != "conversation"),
        select(VocabAttempt.created_at, VocabAttempt.is_correct, VocabItem.language)
        .join(VocabItem, VocabItem.id == VocabAttempt.item_id)
        .where(VocabAttempt.user_id == user_id),
        select(ConversationTurn.created_at, ConversationTurn.is_correct, ConversationTurn.language)
        .where(ConversationTurn.user_id == user_id),
        select(GrammarAttempt.created_at, GrammarAttempt.is_correct, GrammarAttempt.language)
        .where(GrammarAttempt.user_id == user_id),
    ).subquery()
    local_day = func.date(func.timezone(tz, answers.c.created_at))

    lang_filter = [answers.c.language == language] if language else []
    total, correct = (await db.execute(
        select(func.count(), func.coalesce(func.sum(cast(answers.c.is_correct, Integer)), 0)).where(*lang_filter)
    )).one()

    start = today - timedelta(days=days - 1)
    per_day = {
        d: (t, c) for d, t, c in (await db.execute(
            select(local_day, func.count(), func.sum(cast(answers.c.is_correct, Integer)))
            .where(local_day >= start, *lang_filter)
            .group_by(local_day)
        )).all()
    }
    daily = []
    for i in range(days):
        d = start + timedelta(days=i)
        t, c = per_day.get(d, (0, 0))
        daily.append({"date": d, "total": t, "correct": c})

    active_days = set((await db.execute(select(local_day).distinct())).scalars())
    today_count = await db.scalar(select(func.count()).select_from(answers).where(local_day == today))

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
