"""The grammar section: topics of hand-written questions, organised like
lingua.com's grammar pages — categories (Articles, Verbs…) → topics (Ser or
estar…) → sheets of gap sentences with four options.

Data: data/grammar/{language}/index.json lists the categories in order, and each
other file there is one topic:

    {"id", "title", "spanish", "category", "level" (1-5 = A1-C1),
     "rule": ["one line of the rule", …],
     "sheets": [{"title": optional, "questions": [[id, text, answer, [3 wrong options], why], …]}]}

`text` holds one "___" for the gap. Question ids never change once answered
(answers are stored against them); tests/test_grammar_topics.py checks the data.
The "find the mistake" pairs (data/grammar/{language}.json, services/grammar.py)
are one more topic, with a sheet per level and a typed correction.

Answers are graded here, stored in `grammar_attempts`, and a mistake gives the
topic a review box in `grammar_reviews` (same schedule and statuses as the verb
reviews in services/history.py), so it shows up in "Work on this". No LLM.
"""
import functools
import json
import random
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import GrammarAttempt, GrammarReview, Language
from app.services import grammar
from app.services.history import is_due, next_review, review_status

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "grammar"
BLANK = "___"
MISTAKES_TOPIC = "find-the-mistake"
LEVEL_LABELS = {1: "A1", 2: "A2", 3: "B1", 4: "B2", 5: "C1"}
REVIEW_LENGTH = 12
MISTAKES_SHOWN = 5


@dataclass(frozen=True)
class Question:
    id: str
    kind: str                 # "choice": pick the option for the gap | "correct": retype the sentence without its mistake
    text: str                 # choice: the sentence with BLANK | correct: the sentence with the mistake
    answer: str               # choice: the right option | correct: the corrected sentence
    why: str
    options: tuple[str, ...] = ()  # choice: in display order (shuffled once, the same for everyone)
    also: tuple[str, ...] = ()     # correct: other corrections that are just as right

    def filled(self) -> str:
        """The sentence as it should read."""
        return self.text.replace(BLANK, self.answer) if self.kind == "choice" else self.answer


@dataclass(frozen=True)
class Sheet:
    number: int
    title: str | None
    questions: tuple[Question, ...]


@dataclass(frozen=True)
class Topic:
    id: str
    title: str
    spanish: str
    category: str
    level: int | None         # None: spans levels (one sheet per level)
    rule: tuple[str, ...]
    sheets: tuple[Sheet, ...]

    def questions(self) -> dict[str, Question]:
        return {q.id: q for sheet in self.sheets for q in sheet.questions}


@dataclass(frozen=True)
class Category:
    id: str
    title: str


@dataclass(frozen=True)
class Bank:
    categories: tuple[Category, ...]
    topics: dict[str, Topic]  # in display order: by category, then level, then index.json's order


def _choice(topic_id: str, raw: list) -> Question:
    qid, text, answer, wrong, why = raw
    options = [answer, *wrong]
    random.Random(f"{topic_id}/{qid}").shuffle(options)  # stable: the same order on every visit
    return Question(id=qid, kind="choice", text=text, answer=answer, why=why, options=tuple(options))


def _mistakes_topic(language: Language) -> Topic | None:
    pairs = grammar.load_bank(language)
    if not pairs:
        return None
    sheets = []
    for level in sorted({p.level for p in pairs}):
        questions = tuple(
            Question(id=p.id, kind="correct", text=p.wrong, answer=p.correct, why=p.why, also=p.also)
            for p in pairs if p.level == level
        )
        sheets.append(Sheet(number=len(sheets) + 1, title=LEVEL_LABELS[level], questions=questions))
    return Topic(
        id=MISTAKES_TOPIC, title="Find the mistake", spanish="Encuentra el error", category="mixed", level=None,
        rule=("Each sentence has exactly one mistake: type the whole sentence again, corrected.",
              "Capitals and punctuation don't matter; a missing accent counts as almost right."),
        sheets=tuple(sheets),
    )


@functools.cache
def load(language: Language) -> Bank:
    """Every topic for a language (an empty bank if it has none)."""
    folder = DATA_DIR / language.value
    if not (folder / "index.json").exists():
        return Bank((), {})
    index = json.loads((folder / "index.json").read_text(encoding="utf-8"))
    categories = tuple(Category(c["id"], c["title"]) for c in index["categories"])
    category_order = {c.id: i for i, c in enumerate(categories)}
    topic_order = {t: i for i, t in enumerate(index["order"])}

    topics = []
    for path in sorted(folder.glob("*.json")):
        if path.name == "index.json":
            continue
        raw = json.loads(path.read_text(encoding="utf-8"))
        sheets = tuple(
            Sheet(number=i + 1, title=s.get("title"), questions=tuple(_choice(raw["id"], q) for q in s["questions"]))
            for i, s in enumerate(raw["sheets"])
        )
        topics.append(Topic(
            id=raw["id"], title=raw["title"], spanish=raw["spanish"], category=raw["category"],
            level=raw["level"], rule=tuple(raw["rule"]), sheets=sheets,
        ))
    topics.sort(key=lambda t: (category_order[t.category], t.level, topic_order.get(t.id, len(topic_order))))
    if mistakes := _mistakes_topic(language):
        topics.append(mistakes)
    return Bank(categories, {t.id: t for t in topics})


def get_topic(language: Language, topic_id: str) -> Topic | None:
    return load(language).topics.get(topic_id)


# ── Grading and recording ────────────────────────────────────────────────────

@dataclass(frozen=True)
class Graded:
    result: str               # correct | almost | wrong
    explanation: str
    fix: grammar.Fix | None = None


async def grade_answer(db: AsyncSession, language: Language, question: Question, answer: str) -> Graded:
    if question.kind == "choice":
        # An option was clicked: exactly the right one or not (never "almost"; "a El" ≠ "a el")
        return Graded("correct" if answer == question.answer else "wrong", question.why)
    accepted = await grammar.accepted_corrections(db, language, question.answer)
    accepted += [a for a in question.also if a not in accepted]
    graded = grammar.grade_answer(
        {"sentence_with_error": question.text, "corrected_sentence": question.answer, "explanation": question.why},
        answer, accepted,
    )
    return Graded(graded.result, graded.explanation, graded.fix)


async def record_answer(
    db: AsyncSession, user_id: int, language: Language, topic: Topic, question: Question,
    answer: str, graded: Graded, now: datetime,
) -> dict:
    """Store the answer and move the topic's review box. Commits.

    A mistake creates the topic's review (due now); right answers move an
    existing one up when its check-up is due. Returns {"status", "due_at"}.
    """
    is_correct = graded.result == "correct"
    db.add(GrammarAttempt(
        user_id=user_id, language=language, topic=topic.id, question_id=question.id,
        user_answer=answer[:512], is_correct=is_correct, is_almost=graded.result == "almost", created_at=now,
    ))
    review = (await db.execute(
        select(GrammarReview).where(
            GrammarReview.user_id == user_id, GrammarReview.language == language, GrammarReview.topic == topic.id,
        )
    )).scalar_one_or_none()
    if review is None and not is_correct:
        review = GrammarReview(user_id=user_id, language=language, topic=topic.id, box=0, correct_count=0, wrong_count=0)
        db.add(review)
    state = {"status": None, "due_at": None}
    if review is not None:
        review.box, review.due_at = next_review(review.box, review.due_at, is_correct, now)
        review.last_seen_at = now
        if is_correct:
            review.correct_count += 1
        else:
            review.wrong_count += 1
        state = {"status": review_status(review.box, review.wrong_count), "due_at": review.due_at}
    await db.commit()
    return state


# ── Progress ─────────────────────────────────────────────────────────────────

async def latest_answers(
    db: AsyncSession, user_id: int, language: Language, topic_id: str | None = None,
) -> dict[tuple[str, str], bool]:
    """(topic, question id) → whether the latest answer to it was right."""
    query = (
        select(GrammarAttempt.topic, GrammarAttempt.question_id, GrammarAttempt.is_correct)
        .where(GrammarAttempt.user_id == user_id, GrammarAttempt.language == language)
        .ext(distinct_on(GrammarAttempt.topic, GrammarAttempt.question_id))
        .order_by(GrammarAttempt.topic, GrammarAttempt.question_id,
                  GrammarAttempt.created_at.desc(), GrammarAttempt.id.desc())
    )
    if topic_id:
        query = query.where(GrammarAttempt.topic == topic_id)
    return {(t, q): ok for t, q, ok in (await db.execute(query)).all()}


def sheet_progress(topic: Topic, sheet: Sheet, latest: dict[tuple[str, str], bool]) -> dict:
    answers = [latest.get((topic.id, q.id)) for q in sheet.questions]
    return {
        "number": sheet.number, "title": sheet.title, "questions": len(sheet.questions),
        "answered": sum(a is not None for a in answers), "correct": sum(a is True for a in answers),
    }


async def reviews(db: AsyncSession, user_id: int, language: Language) -> dict[str, GrammarReview]:
    return {
        r.topic: r for r in (await db.execute(
            select(GrammarReview).where(GrammarReview.user_id == user_id, GrammarReview.language == language)
        )).scalars()
    }


def review_state(review: GrammarReview | None, now: datetime) -> dict:
    if review is None:
        return {"status": None, "due_at": None, "is_due": False}
    return {
        "status": review_status(review.box, review.wrong_count),
        "due_at": review.due_at, "is_due": is_due(review.due_at, now),
    }


def topic_summary(topic: Topic, latest: dict, review: GrammarReview | None, now: datetime) -> dict:
    sheets = [sheet_progress(topic, s, latest) for s in topic.sheets]
    return {
        "id": topic.id, "title": topic.title, "spanish": topic.spanish, "category": topic.category,
        "level": topic.level, "sheets": sheets,
        "questions": sum(s["questions"] for s in sheets),
        "answered": sum(s["answered"] for s in sheets),
        "correct": sum(s["correct"] for s in sheets),
        **review_state(review, now),
    }


async def overview(db: AsyncSession, user_id: int, language: Language, now: datetime) -> dict:
    """The grammar page: categories, every topic with its progress, and the overall score."""
    bank = load(language)
    latest = await latest_answers(db, user_id, language)
    by_topic = await reviews(db, user_id, language)
    topics = [topic_summary(t, latest, by_topic.get(t.id), now) for t in bank.topics.values()]
    return {
        "categories": [{"id": c.id, "title": c.title} for c in bank.categories],
        "topics": topics,
        "questions": sum(t["questions"] for t in topics),
        "correct": sum(t["correct"] for t in topics),
    }


async def topic_detail(db: AsyncSession, user_id: int, language: Language, topic: Topic, now: datetime) -> dict:
    latest = await latest_answers(db, user_id, language, topic.id)
    review = (await reviews(db, user_id, language)).get(topic.id)
    return {**topic_summary(topic, latest, review, now), "rule": list(topic.rule)}


def question_out(q: Question) -> dict:
    """A question as the browser gets it: no answer until it's been tried."""
    return {"id": q.id, "kind": q.kind, "text": q.text, "options": list(q.options)}


async def review_questions(
    db: AsyncSession, user_id: int, language: Language, topic: Topic, rng: random.Random | None = None,
) -> list[Question]:
    """A review sheet for a topic: questions last answered wrong first, then
    ones never answered, then the rest."""
    rng = rng or random.Random()
    latest = await latest_answers(db, user_id, language, topic.id)
    groups: list[list[Question]] = [[], [], []]
    for q in topic.questions().values():
        answered = latest.get((topic.id, q.id))
        groups[0 if answered is False else 1 if answered is None else 2].append(q)
    for g in groups:
        rng.shuffle(g)
    return (groups[0] + groups[1] + groups[2])[:REVIEW_LENGTH]


# ── For "Work on this" and "My mistakes" ─────────────────────────────────────

async def weak_topics(db: AsyncSession, user_id: int, language: Language, limit: int, now: datetime) -> dict:
    """Topics that need work (most mistakes first), then ones getting there
    (check-up due first); counts per status, how many are due, next check-up."""
    bank = load(language)
    mistaken = [r for r in (await reviews(db, user_id, language)).values() if r.wrong_count and r.topic in bank.topics]
    status = {r.topic: review_status(r.box, r.wrong_count) for r in mistaken}
    needs = sorted((r for r in mistaken if status[r.topic] == "needs_work"), key=lambda r: (-r.wrong_count, r.topic))
    getting = sorted((r for r in mistaken if status[r.topic] == "getting_there"), key=lambda r: r.due_at)
    return {
        "items": [
            {"topic": r.topic, "title": bank.topics[r.topic].title, "status": status[r.topic],
             "due_at": r.due_at, "is_due": is_due(r.due_at, now), "mistakes": r.wrong_count}
            for r in (needs + getting)[:limit]
        ],
        "counts": {s: sum(v == s for v in status.values()) for s in ("needs_work", "getting_there", "fixed")},
        "due_count": sum(1 for r in mistaken if status[r.topic] != "fixed" and is_due(r.due_at, now)),
        "next_check_up_at": min((r.due_at for r in getting if not is_due(r.due_at, now)), default=None),
    }


async def mistake_history(db: AsyncSession, user_id: int, language: Language, now: datetime) -> list[dict]:
    """Every grammar topic ever got wrong, with its status and latest wrong answers."""
    bank = load(language)
    mistaken = [r for r in (await reviews(db, user_id, language)).values() if r.wrong_count and r.topic in bank.topics]
    if not mistaken:
        return []
    wrong: dict[str, list[GrammarAttempt]] = {}
    for a in (await db.execute(
        select(GrammarAttempt).where(
            GrammarAttempt.user_id == user_id, GrammarAttempt.language == language,
            GrammarAttempt.is_correct.is_(False),
        ).order_by(GrammarAttempt.created_at.desc(), GrammarAttempt.id.desc())
    )).scalars():
        wrong.setdefault(a.topic, []).append(a)

    groups = []
    for r in mistaken:
        topic = bank.topics[r.topic]
        questions = topic.questions()
        answers = [a for a in wrong.get(r.topic, []) if a.question_id in questions]
        groups.append({
            "topic": topic.id, "title": topic.title, "status": review_status(r.box, r.wrong_count),
            "due_at": r.due_at, "is_due": is_due(r.due_at, now), "last_seen_at": r.last_seen_at,
            "total_mistakes": len(answers),
            "mistakes": [
                {"question": questions[a.question_id].text, "user_answer": a.user_answer,
                 "expected": questions[a.question_id].answer, "is_almost": a.is_almost, "created_at": a.created_at}
                for a in answers[:MISTAKES_SHOWN]
            ],
            "last_mistake_at": answers[0].created_at if answers else None,
        })
    order = {"needs_work": 0, "getting_there": 1, "fixed": 2}
    groups.sort(key=lambda g: (order[g["status"]], -(g["last_mistake_at"] or g["last_seen_at"]).timestamp()))
    return groups
