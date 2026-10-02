"""Vocabulary: seeding, answer grading, sessions and spaced review.

Words and everyday phrases come from data/vocabulary/{language}.json — chosen
with a subtitle frequency list (FrequencyWords) rather than invented by the
LLM; `rank` there is the word's position in that list. Reviews reuse the
Leitner scheduling from services/history.py.
"""
import json
import random
import re
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Language, VocabAttempt, VocabItem, VocabReview
from app.services.grading import Grade, grade
from app.services.history import next_review
from app.services.sentences import blank_out

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "vocabulary"
VOCAB_LANGUAGES = [Language.spanish, Language.french]

EXERCISES = ("flashcard", "choice_to_native", "choice_to_target", "type_to_target", "type_to_native", "cloze", "dictation")
LEARNED_BOX = 3  # answered right on three separate reviews in a row

_PUNCTUATION = re.compile(r"[¿?¡!.,;:\"«»“”—–()]")


# ── Seeding ──────────────────────────────────────────────────────────────────

def level_from_rank(rank: int | None, kind: str) -> int:
    """Everyday phrases are always A1; words by how common they are."""
    if kind == "phrase" or rank is None or rank <= 1500:
        return 1
    return 2 if rank <= 4000 else 3


def load_entries(language: Language) -> list[dict]:
    """Rows for vocab_items from the language's JSON file ([] if there is none)."""
    path = DATA_DIR / f"{language.value}.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    for topic, entries in data.get("topics", {}).items():
        rows += [_row(language, "word", topic, e) for e in entries]
    rows += [_row(language, "phrase", e.get("topic", "phrases"), e) for e in data.get("phrases", [])]
    return rows


def _row(language: Language, kind: str, topic: str, e: dict) -> dict:
    return {
        "language": language, "kind": kind, "text": e["word"], "article": e.get("article"),
        "translation": e["en"], "pos": e.get("pos"), "topic": topic,
        "level": level_from_rank(e.get("rank"), kind), "frequency_rank": e.get("rank"),
        "example": e["ex"], "example_translation": e["ex_en"],
    }


async def upsert_items(db: AsyncSession, rows: list[dict]) -> int:
    """Insert or update by (language, kind, text), so edits to the JSON propagate. Commits."""
    if not rows:
        return 0
    stmt = pg_insert(VocabItem).values(rows)
    stmt = stmt.on_conflict_do_update(
        # the partial unique index on shared (owner_id IS NULL) items
        index_elements=["language", "kind", "text"],
        index_where=VocabItem.owner_id.is_(None),
        set_={c: stmt.excluded[c] for c in rows[0] if c not in ("language", "kind", "text")},
    )
    await db.execute(stmt)
    await db.commit()
    return len(rows)


def visible_to(user_id: int):
    """Shared items plus the user's own saved words."""
    return or_(VocabItem.owner_id.is_(None), VocabItem.owner_id == user_id)


# ── Grading ──────────────────────────────────────────────────────────────────

def _clean(text: str) -> str:
    return _PUNCTUATION.sub(" ", text.replace("’", "'"))


def with_article(item: VocabItem) -> str:
    if not item.article:
        return item.text
    return f"{item.article}{item.text}" if item.article.endswith("'") else f"{item.article} {item.text}"


def accepted_answers(item: VocabItem, exercise: str) -> list[str]:
    """Every answer that counts as right for this exercise, display form first."""
    if exercise in ("type_to_native", "choice_to_native"):
        answers = []
        for alt in item.translation.split(";"):
            alt = alt.strip()
            bare = re.sub(r"\s*\([^)]*\)", "", alt).strip()  # "fish (food)" → "fish"
            for a in (alt, bare):
                answers.append(a)
                answers.append(re.sub(r"^(to|the|a|an) ", "", a))  # "to eat" ~ "eat", "the bill" ~ "bill"
        return list(dict.fromkeys(a for a in answers if a))
    if exercise == "cloze":
        return [item.text]
    if exercise == "dictation":
        # Phrases are short enough to dictate whole; words are heard in their example sentence
        return [item.text if item.kind == "phrase" else item.example]
    return list(dict.fromkeys([item.text, with_article(item)]))


def grade_answer(item: VocabItem, exercise: str, answer: str) -> tuple[Grade, list[str]]:
    accepted = accepted_answers(item, exercise)
    targets = [_clean(a) for a in accepted]
    tries = [answer]
    if exercise in ("type_to_native", "choice_to_native"):
        # English answers may come with or without "to"/"the"/"a": "the house" ~ "house"
        tries.append(re.sub(r"^\s*(to|the|a|an)\s+", "", answer, flags=re.IGNORECASE))
    grades = [grade(_clean(t), targets) for t in tries]
    best = next((g for g in grades if g.is_correct), None) or next((g for g in grades if g.is_almost), grades[0])
    return best, accepted


def cloze(item: VocabItem) -> str | None:
    """The example sentence with the item blanked out (None if it can't be blanked cleanly)."""
    return blank_out(item.example, [item.text])


# ── Sessions ─────────────────────────────────────────────────────────────────

async def distractors(db: AsyncSession, item: VocabItem, n: int = 3, rng: random.Random | None = None) -> list[VocabItem]:
    """Wrong options for multiple choice: same kind (and part of speech), same topic first."""
    rng = rng or random.Random()
    # Options always come from the shared list; a personal word competes with shared words
    query = select(VocabItem).where(
        VocabItem.language == item.language,
        VocabItem.kind == ("word" if item.kind == "personal" else item.kind),
        VocabItem.owner_id.is_(None),
        VocabItem.id != item.id,
    )
    if item.pos:
        query = query.where(VocabItem.pos == item.pos)
    pool = list((await db.execute(query)).scalars())
    same_topic = [p for p in pool if p.topic == item.topic]
    others = [p for p in pool if p.topic != item.topic]
    rng.shuffle(same_topic)
    rng.shuffle(others)
    picks = []
    for p in same_topic + others:
        # Options must look different from the answer and from each other
        if p.translation.split(";")[0] != item.translation.split(";")[0] and all(p.text != q.text for q in picks):
            picks.append(p)
        if len(picks) == n:
            break
    return picks


async def build_session(
    db: AsyncSession, user_id: int, language: Language, kind: str | None, topic: str | None,
    count: int, now: datetime, rng: random.Random | None = None,
) -> list[dict]:
    """Due reviews first, then new items (most common first), then the weakest seen ones."""
    rng = rng or random.Random()
    scope = [VocabItem.language == language, visible_to(user_id)]
    if kind:
        scope.append(VocabItem.kind == kind)
    if topic:
        scope.append(VocabItem.topic == topic)

    reviews = {
        r.item_id: r for r in (await db.execute(
            select(VocabReview).join(VocabItem, VocabItem.id == VocabReview.item_id)
            .where(VocabReview.user_id == user_id, *scope)
        )).scalars()
    }
    items = list((await db.execute(
        select(VocabItem).where(*scope).order_by(VocabItem.level, VocabItem.frequency_rank.nulls_last(), VocabItem.id)
    )).scalars())

    due = sorted((i for i in items if i.id in reviews and reviews[i.id].due_at <= now),
                 key=lambda i: (reviews[i.id].box, reviews[i.id].due_at))
    new = [i for i in items if i.id not in reviews]
    weak = sorted((i for i in items if i.id in reviews and reviews[i.id].due_at > now),
                  key=lambda i: (reviews[i.id].box, reviews[i.id].due_at))
    chosen = (due + new + weak)[:count]
    rng.shuffle(chosen)

    session = []
    for item in chosen:
        review = reviews.get(item.id)
        session.append({
            **item_dict(item),
            "box": review.box if review else None,
            "is_new": review is None,
            "cloze": cloze(item),
            "options": [item_dict(d) for d in await distractors(db, item, rng=rng)],
        })
    return session


def item_dict(item: VocabItem) -> dict:
    return {
        "id": item.id, "kind": item.kind, "text": item.text, "article": item.article,
        "display": with_article(item), "translation": item.translation, "pos": item.pos,
        "topic": item.topic, "level": item.level,
        "example": item.example, "example_translation": item.example_translation,
    }


# ── Recording ────────────────────────────────────────────────────────────────

async def record(
    db: AsyncSession, user_id: int, item: VocabItem, exercise: str, answer: str,
    is_correct: bool, is_almost: bool, now: datetime | None = None,
) -> VocabReview:
    """Store the answer and move the item's review box. Commits."""
    now = now or datetime.now(timezone.utc)
    db.add(VocabAttempt(
        user_id=user_id, item_id=item.id, exercise=exercise, user_answer=answer[:256],
        is_correct=is_correct, is_almost=is_almost and not is_correct, created_at=now,
    ))
    review = (await db.execute(
        select(VocabReview).where(VocabReview.user_id == user_id, VocabReview.item_id == item.id)
    )).scalar_one_or_none()
    if review is None:
        review = VocabReview(user_id=user_id, item_id=item.id, box=0, correct_count=0, wrong_count=0)
        db.add(review)
    review.box, review.due_at = next_review(review.box, is_correct, now)
    review.last_seen_at = now
    if is_correct:
        review.correct_count += 1
    else:
        review.wrong_count += 1
    await db.commit()
    return review


# ── Overview ─────────────────────────────────────────────────────────────────

async def overview(db: AsyncSession, user_id: int, language: Language, now: datetime) -> dict:
    """Per kind+topic: how many items, how many seen, learned and due for this user."""
    rows = (await db.execute(
        select(
            VocabItem.kind, VocabItem.topic,
            func.count(VocabItem.id),
            func.count(VocabReview.id),
            func.count(VocabReview.id).filter(VocabReview.box >= LEARNED_BOX),
            func.count(VocabReview.id).filter(VocabReview.due_at <= now),
        )
        .outerjoin(VocabReview, (VocabReview.item_id == VocabItem.id) & (VocabReview.user_id == user_id))
        .where(VocabItem.language == language, visible_to(user_id))
        .group_by(VocabItem.kind, VocabItem.topic)
    )).all()
    groups = [
        {"kind": kind, "topic": topic, "total": total, "seen": seen, "learned": learned, "due": due}
        for kind, topic, total, seen, learned, due in rows
    ]
    return {
        "available": bool(groups),
        "groups": groups,
        "total": sum(g["total"] for g in groups),
        "learned": sum(g["learned"] for g in groups),
        "due": sum(g["due"] for g in groups),
    }
