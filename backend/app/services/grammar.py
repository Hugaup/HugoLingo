"""Find the mistake: a sentence with exactly one mistake, to type out corrected.

The exercises are hand-written pairs in data/grammar/{language}.json (original
sentences; tests/test_grammar.py checks each pair differs by one small change).
Served as the "Find the mistake" topic of the grammar section
(services/grammar_topics.py); this module compares sentences and grades a typed
correction. No LLM is involved.
"""
import functools
import json
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Language, VerbConjugation
from app.services.conversation import fold

MAX_CHANGED_WORDS = 3     # the mistake and its fix are each at most this many words

# ── Words and the one change between two sentences ───────────────────────────

_TOKEN = re.compile(r"[^\W_]+(?:'[^\W_]+)*")


@dataclass(frozen=True)
class Token:
    word: str   # lowercased
    start: int
    end: int


def tokens(text: str) -> list[Token]:
    """Words with their positions; punctuation and capitals never count (same words as conversation.words)."""
    return [Token(m.group().lower(), m.start(), m.end()) for m in _TOKEN.finditer(text.replace("’", "'"))]


def _words(text: str) -> list[str]:
    return [t.word for t in tokens(text)]


def _one_change(a: list[str], b: list[str]) -> tuple[int, int, int, int] | None:
    """(i1, i2, j1, j2) of the single differing span a[i1:i2] → b[j1:j2], or None."""
    ops = [op for op in SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes() if op[0] != "equal"]
    if len(ops) != 1:
        return None
    _, i1, i2, j1, j2 = ops[0]
    if max(i2 - i1, j2 - j1) > MAX_CHANGED_WORDS:
        return None
    # "is build" → "are built" is two mistakes: words swapped one for one may differ only once
    if i2 - i1 == j2 - j1 and sum(x != y for x, y in zip(a[i1:i2], b[j1:j2])) > 1:
        return None
    return i1, i2, j1, j2


@dataclass(frozen=True)
class Fix:
    """The correction, laid out for display: before + (wrong → right) + after."""
    wrong: str   # the mistaken words as written in the sentence with the error ("" if a word is missing)
    right: str   # their correction as written in the corrected sentence ("" if a word must go)
    before: str  # the corrected sentence up to the correction
    after: str   # and after it


def find_fix(with_error: str, corrected: str) -> Fix | None:
    """The one small change that turns `with_error` into `corrected`; None if there isn't exactly one."""
    a, b = tokens(with_error), tokens(corrected)
    change = _one_change([t.word for t in a], [t.word for t in b])
    if change is None:
        return None
    i1, i2, j1, j2 = change
    wrong = with_error[a[i1].start:a[i2 - 1].end] if i2 > i1 else ""
    if j2 > j1:
        start, end = b[j1].start, b[j2 - 1].end
    elif j1 < len(b):
        start = end = b[j1].start
    else:  # the extra word was the last one
        start = end = b[-1].end
        return Fix(wrong, "", corrected[:start] + " ", corrected[end:])
    return Fix(wrong, corrected[start:end], corrected[:start], corrected[end:])



# ── The hand-written pairs ───────────────────────────────────────────────────

BANK_DIR = Path(__file__).resolve().parents[2] / "data" / "grammar"


@dataclass(frozen=True)
class BankItem:
    id: str     # stable: answers are stored against it
    level: int
    type: str
    correct: str
    wrong: str
    why: str
    also: tuple[str, ...] = ()  # other corrections that are just as right (para la que / para la cual)


@functools.cache
def load_bank(language: Language) -> tuple[BankItem, ...]:
    """The hand-written exercises in data/grammar/{language}.json (none if there is no file)."""
    path = BANK_DIR / f"{language.value}.json"
    if not path.exists():
        return ()
    items = json.loads(path.read_text(encoding="utf-8"))["items"]
    return tuple(BankItem(**{**item, "also": tuple(item.get("also", ()))}) for item in items)


# ── Grading an answer ────────────────────────────────────────────────────────

@dataclass(frozen=True)
class GrammarGrade:
    result: str  # correct | almost | wrong
    explanation: str
    fix: Fix | None


def _contains(haystack: list[str], needle: list[str]) -> bool:
    n = len(needle)
    return any(haystack[i:i + n] == needle for i in range(len(haystack) - n + 1))


def _sentence(*parts: str) -> str:
    return " ".join(p for p in parts if p)


_SPANISH_IMPERFECT_SUBJ = ("Subjuntivo pretérito imperfecto (1)", "Subjuntivo pretérito imperfecto (2)")


async def _ra_se_twins(db: AsyncSession, words: set[str]) -> dict[str, str]:
    """Spanish imperfect subjunctives and their twin spelling: {"vinieras": "vinieses", "hubiese": "hubiera"}."""
    rows = (await db.execute(
        select(VerbConjugation.verb_infinitive, VerbConjugation.person, VerbConjugation.tense,
               func.lower(VerbConjugation.form))
        .where(VerbConjugation.language == Language.spanish,
               VerbConjugation.tense.in_(_SPANISH_IMPERFECT_SUBJ),
               VerbConjugation.verb_infinitive.in_(
                   select(VerbConjugation.verb_infinitive).where(
                       VerbConjugation.language == Language.spanish,
                       VerbConjugation.tense.in_(_SPANISH_IMPERFECT_SUBJ),
                       func.lower(VerbConjugation.form).in_(words))))
    )).all()
    by_slot: dict[tuple[str, str], dict[str, str]] = {}
    for verb, person, tense, form in rows:
        by_slot.setdefault((verb, person), {})[tense] = form
    twins = {}
    for forms in by_slot.values():
        ra, se = forms.get(_SPANISH_IMPERFECT_SUBJ[0]), forms.get(_SPANISH_IMPERFECT_SUBJ[1])
        if ra and se:
            twins.update({ra: se, se: ra})
    return {w: t for w, t in twins.items() if w in words}


def _swap_words(sentence: str, swaps: dict[str, str]) -> str:
    out, last = [], 0
    for t in tokens(sentence):
        if t.word in swaps:
            out += [sentence[last:t.start], swaps[t.word]]
            last = t.end
    return "".join(out) + sentence[last:]


async def accepted_corrections(db: AsyncSession, language: Language, corrected: str) -> list[str]:
    """Every correction to accept: the exercise's own, the bank's equally right
    alternatives, and in Spanish the -ra/-se twin of an imperfect subjunctive
    (vinieras = vinieses, hubiera = hubiese)."""
    accepted = [corrected]
    for b in load_bank(language):
        if _words(b.correct) == _words(corrected):
            accepted += b.also
    if language == Language.spanish:
        if twins := await _ra_se_twins(db, {w for sentence in accepted for w in _words(sentence)}):
            accepted += [_swap_words(sentence, twins) for sentence in accepted]
    return list(dict.fromkeys(accepted))


def grade_answer(content: dict, answer: str, accepted: list[str] | None = None) -> GrammarGrade:
    """Grade a typed correction against `accepted` (default: the exercise's own).
    Capitals, punctuation and spacing never count; an accent-only difference is
    "almost" (still a mistake)."""
    corrected = str(content.get("corrected_sentence", ""))
    with_error = str(content.get("sentence_with_error", ""))
    explanation = str(content.get("explanation", "")).strip()
    fix = find_fix(with_error, corrected) if with_error else None
    given, expected = _words(answer), _words(corrected)
    right_answers = [_words(a) for a in (accepted or [corrected])]

    if given and given in right_answers:
        return GrammarGrade("correct", explanation, fix)
    if given and any([fold(w) for w in given] == [fold(w) for w in r] for r in right_answers):
        return GrammarGrade("almost", _sentence("Almost — just the accents.", explanation), fix)

    if fix is None:  # an older exercise without one clear change
        return GrammarGrade("wrong", _sentence(f"The corrected sentence is: '{corrected}'.", explanation), None)
    change = f"{fix.wrong or '…'} → {fix.right or '(remove it)'}"
    error_words = _words(with_error)
    i1, i2, j1, j2 = _one_change(error_words, expected)
    # The mistake with a word of context each side, before and after fixing it
    mistake_seen = error_words[max(i1 - 1, 0):i2 + 1]
    fixed_seen = expected[max(j1 - 1, 0):j2 + 1]
    if given == error_words:
        note = f"The mistake is still there: {change}."
    elif _contains(given, fixed_seen) and not _contains(given, mistake_seen):
        note = f"You fixed the mistake ({change}), but changed something else too."
    else:
        note = f"The mistake was: {change}."
    return GrammarGrade("wrong", _sentence(note, explanation), fix)
