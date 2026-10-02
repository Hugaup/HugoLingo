"""AI conversation practice: role-play scenarios, in-character replies, and a
separate check of every learner message.

The reply and the check are two LLM calls on purpose: the reply streams so the
conversation feels live, and the check is a short low-temperature JSON call
whose prompt was tuned to fix real mistakes only (docs/llm-benchmark.md, run 3).
A wrong "correction" teaches a mistake, so when in doubt we keep the message.
"""
import json
import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ConversationTurn, Language, VerbConjugation
from app.services import explain, history, sentence_pool
from app.services.exercise_gen import LANGUAGE_NAMES
from app.services.grading import Grade
from app.services.llm import LLMClient, llm_client


@dataclass(frozen=True)
class Scenario:
    id: str
    title: str
    description: str
    goal: str       # shown to the learner; also tells the AI where to steer
    ai_role: str
    user_role: str


SCENARIOS = [
    Scenario("cafe", "At the café", "Order something to drink and eat.",
             "Order a drink and something to eat, then ask for the bill.",
             "a friendly waiter in a café", "a customer"),
    Scenario("directions", "Asking the way", "You're lost in town and need help.",
             "Find out how to get to the train station and how long it takes.",
             "a helpful local in the street", "a tourist who is lost"),
    Scenario("hotel", "Hotel check-in", "Arrive at your hotel.",
             "Check in, ask what time breakfast is, and ask for the Wi-Fi password.",
             "a hotel receptionist", "a guest arriving at the hotel"),
    Scenario("shop", "Clothes shopping", "Buy something to wear.",
             "Find a jumper in your size and colour, and ask how much it costs.",
             "a shop assistant in a clothes shop", "a customer"),
    Scenario("new_friend", "Meeting someone new", "Chat with someone you just met.",
             "Introduce yourself, say where you're from, and talk about what you like doing.",
             "a friendly person the learner has just met at a party", "a guest at the party"),
    Scenario("pharmacy", "At the pharmacy", "You're not feeling well.",
             "Explain that you have a headache and a sore throat, and ask what you should take.",
             "a pharmacist", "a customer who feels ill"),
    Scenario("free", "Free chat", "Talk about anything you like.",
             "Chat about your day, your plans, or anything else.",
             "a friendly native speaker who enjoys chatting", "a learner practising conversation"),
]
SCENARIOS_BY_ID = {s.id: s for s in SCENARIOS}

LEVELS = {
    1: ("A1", "Use very simple, common words and short sentences, mostly in the present tense."),
    2: ("A2", "Use simple, everyday words and short sentences; the present, the near future and simple past tenses are fine."),
    3: ("B1", "Speak naturally but clearly; avoid rare words and idioms."),
    4: ("B2", "Speak naturally, as you would with a fluent non-native speaker."),
    5: ("C1", "Speak completely naturally."),
}

MAX_HISTORY = 20  # messages sent back to the model; older ones are dropped


class CheckFailed(Exception):
    """The LLM gave no usable answer when checking a message."""


# ── Replies ──────────────────────────────────────────────────────────────────

def reply_messages(language: Language, scenario: Scenario, level: int, history_: list[dict]) -> list[dict]:
    """The chat to send for the AI's next in-character line (its first one when history_ is empty)."""
    lang = LANGUAGE_NAMES[language]
    code, guidance = LEVELS.get(level, LEVELS[2])
    system = (
        f"This is a role-play to help someone practise {lang}. You are {scenario.ai_role}; "
        f"the learner is {scenario.user_role}. The learner's goal: {scenario.goal}\n"
        f"Rules:\n"
        f"- Write only in {lang}, the way {scenario.ai_role} would speak, with no English words. "
        f"One to three short sentences.\n"
        f"- The learner's level is {code}. {guidance}\n"
        f"- Stay in character and keep the conversation going, usually by asking a question.\n"
        f"- Never correct the learner's mistakes and never translate: that is done separately."
    )
    if not history_:
        return [{"role": "system", "content": system},
                {"role": "user", "content": "(Start the conversation with your first line.)"}]
    return [{"role": "system", "content": system}, *history_[-MAX_HISTORY:]]


# ── Checking a message ───────────────────────────────────────────────────────

CHECK_PROMPT = """You check one message written by someone learning {lang} (level {level}) in a role-play chat.
Fix only real mistakes. Check in particular:
- the verb form: person, tense, and the right verb or auxiliary (ser/estar, avoir/être)
- agreement of articles and adjectives with the noun's gender and number
- spelling and accents
Leave everything that is correct exactly as written: word choice, style, punctuation, capitals. If you are not sure something is a mistake, leave it.
Reply with JSON: {{"corrected": "<the learner's message with only the mistakes fixed - identical if there are none>", "explanation": "<one short sentence in English about the main fix, or empty if none>"}}"""


@dataclass(frozen=True)
class Correction:
    result: str                 # correct | almost | wrong
    corrected: str | None       # None when the message was right
    explanation: str | None


_TOKEN = re.compile(r"[^\W_]+(?:'[^\W_]+)*")


def words(text: str) -> list[str]:
    """Lowercased words, accents kept, punctuation dropped (so ¿?¡!, commas and capitals never count)."""
    return _TOKEN.findall(text.lower().replace("’", "'"))


def fold(word: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", word) if unicodedata.category(c) != "Mn")


def classify(message: str, corrected: object, explanation: object, previous: str | None = None) -> Correction:
    """Turn the model's answer into a grade. Untrustworthy answers count as "no mistake"."""
    ok = Correction("correct", None, None)
    if not isinstance(corrected, str) or not corrected.strip():
        return ok
    said, fixed = words(message), words(corrected)
    if not said or said == fixed:
        return ok  # only punctuation or capitals changed
    # The model sometimes rewrites the message or pastes the other person's
    # line into it: that's not a correction we can show.
    if SequenceMatcher(a=said, b=fixed, autojunk=False).ratio() < 0.5:
        return ok
    if previous and len(fixed) > len(said) and " ".join(fixed).startswith(" ".join(words(previous))):
        return ok
    why = explanation.strip()[:500] if isinstance(explanation, str) and explanation.strip() else None
    result = "almost" if [fold(w) for w in said] == [fold(w) for w in fixed] else "wrong"
    return Correction(result, corrected.strip()[:1000], why)


def check_messages(language: Language, level: int, previous: str | None, message: str) -> list[dict]:
    code, _ = LEVELS.get(level, LEVELS[2])
    context = f'The other person said: "{previous}"\n' if previous else ""
    return [
        {"role": "system", "content": CHECK_PROMPT.format(lang=LANGUAGE_NAMES[language], level=code)},
        {"role": "user", "content": f'{context}The learner replied: "{message}"'},
    ]


async def check_message(
    language: Language, level: int, previous: str | None, message: str, client: LLMClient | None = None,
) -> Correction:
    client = client or llm_client
    try:
        with sentence_pool.live_request():
            data = await client.chat_json(
                check_messages(language, level, previous, message), max_tokens=200, temperature=0,
            )
    except (json.JSONDecodeError, httpx.HTTPStatusError, httpx.RequestError) as e:
        raise CheckFailed(str(e)) from e
    if not isinstance(data, dict):
        raise CheckFailed("not a JSON object")
    return classify(message, data.get("corrected"), data.get("explanation"), previous)


# ── Recording ────────────────────────────────────────────────────────────────

async def verb_mistakes(
    db: AsyncSession, language: Language, message: str, corrected: str,
) -> list[history.AttemptIn]:
    """Words the correction replaced with a form of a verb, as attempts for that verb.

    "Yo querer un café" → "Yo quiero un café" is a mistake on querer, Indicativo
    presente, 1s. Mood/tense/person are kept only when the corrected form pins
    them down; an ambiguous form (French "travaille": present or subjunctive)
    still counts against the verb.
    """
    said, fixed = words(message), words(corrected)
    pairs = []
    for op, i1, i2, j1, j2 in SequenceMatcher(a=said, b=fixed, autojunk=False).get_opcodes():
        if op == "replace" and i2 - i1 == j2 - j1:
            pairs += zip(said[i1:i2], fixed[j1:j2])
    if not pairs:
        return []

    rows = (await db.execute(
        select(VerbConjugation.verb_infinitive, VerbConjugation.mood, VerbConjugation.tense,
               VerbConjugation.person, func.lower(VerbConjugation.form))
        .where(VerbConjugation.language == language,
               func.lower(VerbConjugation.form).in_({w for pair in pairs for w in pair}))
    )).all()
    by_form: dict[str, list] = {}
    for r in rows:
        by_form.setdefault(r[4], []).append(r)

    attempts = []
    for wrong, right in pairs:
        right_rows = by_form.get(right, [])
        verbs = {r.verb_infinitive for r in right_rows}
        # A reflexive twin conjugates the same (voy: ir and irse): keep the plain verb
        verbs = {v for v in verbs if not (v.endswith("se") and v[:-2] in verbs)}
        if len(verbs) > 1:  # e.g. "fui" is ir and ser: trust the verb the learner was using
            verbs &= {r.verb_infinitive for r in by_form.get(wrong, [])}
        if len(verbs) != 1:
            continue
        verb = verbs.pop()
        forms = [r for r in right_rows if r.verb_infinitive == verb]
        tenses = {(r.mood, r.tense) for r in forms}
        persons = {r.person for r in forms}
        personal = len(tenses) == 1 and persons <= set(history.PERSON_ORDER)
        mood, tense = tenses.pop() if personal else (None, None)
        attempts.append(history.AttemptIn(
            verb_infinitive=verb, mood=mood, tense=tense,
            person=persons.pop() if personal and len(persons) == 1 else None,
            user_answer=wrong, expected=right, is_correct=False, is_almost=fold(wrong) == fold(right),
        ))
    return attempts


async def verb_explanation(db: AsyncSession, language: Language, mistake: history.AttemptIn) -> str | None:
    """The rule-based one-liner (same as the drills) when the verb form is pinned down."""
    if not (mistake.mood and mistake.tense and mistake.person):
        return None
    graded = Grade("almost", mistake.expected) if mistake.is_almost else Grade("wrong")
    data = await explain.explain_mistake(
        db, language, mistake.verb_infinitive, mistake.mood, mistake.tense, mistake.person,
        mistake.user_answer, graded, mistake.expected,
    )
    return data["summary"]


@dataclass(frozen=True)
class RecordedTurn:
    correction: Correction
    verb_mistakes: list[history.AttemptIn]


async def record_turn(
    db: AsyncSession, user_id: int, language: Language, scenario: str, message: str, correction: Correction,
) -> RecordedTurn:
    """Store the message and its grade; verb mistakes also go to the shared history. Commits.

    For a verb mistake the conjugation data explains it better than the model
    (which sometimes describes the fix wrongly), so its explanation replaces the model's.
    """
    mistakes = []
    if correction.corrected:
        mistakes = await verb_mistakes(db, language, message, correction.corrected)
        for m in mistakes:
            if why := await verb_explanation(db, language, m):
                correction = Correction(correction.result, correction.corrected, why)
                break
    db.add(ConversationTurn(
        user_id=user_id, language=language, scenario=scenario, message=message[:1000],
        corrected=correction.corrected, explanation=correction.explanation,
        is_correct=correction.result == "correct", is_almost=correction.result == "almost",
    ))
    if mistakes:
        await history.record_attempts(db, user_id, language, "conversation", mistakes)  # commits both
    else:
        await db.commit()
    return RecordedTurn(correction, mistakes)
