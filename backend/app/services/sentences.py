"""Fill-in-the-blank sentence generation for conjugation practice.

Shared by the /conjugation-exercises router, the background sentence pool
(services/sentence_pool.py) and scripts/benchmark_llm.py, so all three use the
exact same prompt and the same validity checks.
"""
import json
import re

import httpx
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Language, VerbConjugation
from app.routers.verbs import COMMON_VERBS
from app.schemas import SentenceExerciseItem, TenseFilter
from app.services.conjugation_utils import PRONOUNS, canonical_tense, resolve_compound_form, variant_tense_names
from app.services.exercise_gen import LANGUAGE_NAMES
from app.services.llm import LLMClient, llm_client

# A sentence + subject in JSON is ~60-120 tokens; the cap stops runaway output
SENTENCE_MAX_TOKENS = 200

# The everyday tenses learners drill most, spelled as stored in verb_conjugations.
# Used to pre-generate the sentence pool and by scripts/benchmark_llm.py.
COMMON_TENSES: dict[Language, list[tuple[str, str]]] = {
    Language.spanish: [
        ("Indicativo", "Indicativo presente"),
        ("Indicativo", "Indicativo pretérito perfecto simple"),
        ("Indicativo", "Indicativo pretérito imperfecto"),
        ("Indicativo", "Indicativo futuro"),
        ("Indicativo", "Indicativo pretérito perfecto compuesto"),
        ("Subjuntivo", "Subjuntivo presente"),
    ],
    Language.french: [
        ("Indicatif", "Présent"),
        ("Indicatif", "Imparfait"),
        ("Indicatif", "Futur"),
        ("Subjonctif", "Présent"),
        ("Conditionnel", "Présent"),
    ],
    Language.english: [
        ("indicative", "indicative present"),
        ("indicative", "indicative past tense"),
        ("indicative", "indicative present continuous"),
        ("indicative", "indicative present perfect"),
    ],
}


class NoConjugationData(Exception):
    """No verb_conjugations row matches the requested tenses."""


def _sibling_variant_tense(tense: str) -> str | None:
    """The other "(1)"/"(2)" spelling-variant tense name, if `tense` is one."""
    if tense.endswith(" (1)"):
        return tense[:-4] + " (2)"
    if tense.endswith(" (2)"):
        return tense[:-4] + " (1)"
    return None


# The canonical pronoun to tell the model to build the sentence around, so it
# can't drift onto a different grammatical person than the one it's supposed
# to conjugate for (e.g. writing "mis amigos" — implying "yo" — around a "tú"
# form: "Cuando era niño, ___ la puerta..." / correct answer "cerrabas").
_PRIMARY_PRONOUN = PRONOUNS

# Reverse lookup: a recognized subject pronoun -> the grammatical person(s) it
# can represent. Used only to catch the clearest failures (the model's own
# subject_hint is itself a pronoun, just the wrong one) — a name/noun phrase
# isn't in here and is let through unchecked, since validating those needs
# real NLU.
_PRONOUN_PERSONS: dict[Language, dict[str, set[str]]] = {
    Language.spanish: {
        "yo": {"1s"},
        "tú": {"2s"}, "tu": {"2s"}, "vos": {"2s"},
        "él": {"3s"}, "el": {"3s"}, "ella": {"3s"}, "usted": {"3s"}, "ud": {"3s"}, "ud.": {"3s"},
        "nosotros": {"1p"}, "nosotras": {"1p"},
        "vosotros": {"2p"}, "vosotras": {"2p"},
        "ellos": {"3p"}, "ellas": {"3p"}, "ustedes": {"3p"}, "uds": {"3p"}, "uds.": {"3p"},
    },
    Language.french: {
        "je": {"1s"}, "j'": {"1s"},
        "tu": {"2s"},
        "il": {"3s"}, "elle": {"3s"}, "on": {"3s"},
        "nous": {"1p"},
        "vous": {"2p"},
        "ils": {"3p"}, "elles": {"3p"},
    },
    Language.english: {
        "i": {"1s"},
        "you": {"2s", "2p"},
        "he": {"3s"}, "she": {"3s"}, "it": {"3s"},
        "we": {"1p"},
        "they": {"3p"},
    },
}


def _subject_hint_conflicts(language: Language, person: str, subject_hint: str) -> bool:
    valid_persons = _PRONOUN_PERSONS.get(language, {}).get(subject_hint.strip().lower())
    if valid_persons is None:
        return False  # not a recognized pronoun (a name/noun phrase) — can't validate, allow it
    return person not in valid_persons


# A blank as its own token: exactly one run of 2+ underscores, with no letter
# directly touching either side. Catches malformed output like "Trabajar___"
# (blank glued straight onto the previous word) or "____ís" (a stray suffix
# fragment left stuck to the blank) — both slipped past a plain
# `"___" in sentence` check since they still technically contain "___".
def _has_one_clean_blank(sentence: str) -> bool:
    runs = list(re.finditer(r"_+", sentence))
    if len(runs) != 1:
        return False
    match = runs[0]
    if len(match.group()) < 2:
        return False
    before = sentence[match.start() - 1] if match.start() > 0 else " "
    after = sentence[match.end()] if match.end() < len(sentence) else " "
    return not before.isalpha() and not after.isalpha()


def _sentence_is_valid(
    sentence: str, subject_hint: str, correct_form: str, alternates: list[str], language: Language, person: str,
) -> bool:
    """Reject LLM output that doesn't actually make a valid fill-in-the-blank:
    no blank, more than one blank, a blank glued onto adjacent text instead of
    standing alone, the target form leaked into the text instead of being
    replaced by '___' (e.g. an obscure verb the model couldn't confidently
    blank out), or a subject that contradicts the required person."""
    if not sentence or not subject_hint:
        return False
    if not _has_one_clean_blank(sentence):
        return False
    if any(form.lower() in sentence.lower() for form in [correct_form, *alternates]):
        return False
    if _subject_hint_conflicts(language, person, subject_hint):
        return False
    return True


PERSON_DESC = {
    "1s": "1st person singular",
    "2s": "2nd person singular",
    "3s": "3rd person singular",
    "1p": "1st person plural",
    "2p": "2nd person plural",
    "3p": "3rd person plural",
}

# What context clue makes a given tense the ONLY grammatically valid choice for
# the blank, keyed by (mood, canonical tense) — both lowercased. Without this,
# the model tends to just conjugate correctly without giving any clue *why*
# that tense is required, so e.g. an imperfecto sentence ends up reading
# equally well as presente ("Nosotros ___ en una gran casa..." fits both
# "vivimos" and "vivíamos" with zero context to prefer one over the other).
_DISAMBIGUATION_HINTS: dict[Language, dict[tuple[str, str], str]] = {
    Language.spanish: {
        ("indicativo", "indicativo presente"):
            "a habitual/general-truth marker (e.g. 'todos los días', 'siempre', 'los lunes') — not a past or future moment",
        ("indicativo", "indicativo pretérito imperfecto"):
            "a clear ongoing/habitual PAST marker (e.g. 'cuando era niño/a', 'en aquella época', 'todos los días' combined with past narration) — it must NOT read as a present habit or a single completed past event",
        ("indicativo", "indicativo pretérito perfecto simple"):
            "a single, completed past event at a specific point in time (e.g. 'ayer', 'el año pasado', 'una vez', 'en 2010') — not a habitual or ongoing past action",
        ("indicativo", "indicativo pretérito perfecto compuesto"):
            "a still-open time period with present relevance (e.g. 'hoy', 'esta semana', 'ya', 'todavía no') — not a closed, finished-and-dated past moment",
        ("indicativo", "indicativo pretérito pluscuamperfecto"):
            "two sequential past events, where this action clearly happened BEFORE another past action (e.g. 'cuando llegué, ya ___', 'antes de eso')",
        ("indicativo", "indicativo pretérito anterior"):
            "a formal/literary context where this action happened immediately before another past action (right after 'apenas', 'en cuanto', or 'cuando')",
        ("indicativo", "indicativo futuro"):
            "a clear future-time marker (e.g. 'mañana', 'el año que viene', 'pronto') or an explicit prediction/guess about the present",
        ("indicativo", "indicativo futuro perfecto"):
            "a future deadline by which the action will be complete (e.g. 'para las diez', 'antes de que llegues'), or a guess about something already finished",
        ("condicional", "condicional"):
            "a hypothetical, polite-request, or 'would' context — ideally paired with a 'si' clause, or a clearly hypothetical framing",
        ("condicional", "condicional perfecto"):
            "a hypothetical PAST context — an unreal 'if I had...' scenario, ideally paired with a 'si hubiera...' clause",
        ("subjuntivo", "subjuntivo presente"):
            "a clear trigger for subjunctive in the main clause (e.g. 'quiero que', 'es importante que', 'dudo que', 'ojalá', 'para que') describing a present/future wish, doubt, or necessity",
        ("subjuntivo", "subjuntivo pretérito imperfecto"):
            "either a past-tense subjunctive trigger (e.g. 'quería que', 'esperaba que') or a hypothetical 'si' clause contrary to fact (e.g. 'si tuviera...')",
        ("subjuntivo", "subjuntivo futuro"):
            "a formal/legal/literary fixed-expression context — this tense is archaic, so keep it formulaic",
        ("subjuntivo", "subjuntivo pretérito perfecto"):
            "a subjunctive trigger about a recently-completed action (e.g. 'espero que hayas...', 'no creo que haya...')",
        ("subjuntivo", "subjuntivo pretérito pluscuamperfecto"):
            "a hypothetical past regret (e.g. 'ojalá hubiera...') or an unreal 'si hubiera...' clause about something that didn't happen",
        ("subjuntivo", "subjuntivo futuro perfecto"):
            "a formal/legal context — this tense is archaic and rare, keep it formulaic",
        ("imperativo", "imperativo"):
            "a direct positive command addressed to someone, with an exclamation mark",
        ("imperativo", "imperativo non"):
            "a direct NEGATIVE command ('don't do X') addressed to someone, with 'no' and an exclamation mark",
    },
    Language.french: {
        ("indicatif", "présent"):
            "a habitual/general-truth marker (e.g. 'tous les jours', 'toujours') or an action happening right now — not a past or future moment",
        ("indicatif", "imparfait"):
            "a clear ongoing/habitual PAST marker (e.g. 'quand j'étais enfant', 'à cette époque', 'tous les jours' combined with past narration) — it must NOT read as a present habit or a single completed past event",
        ("indicatif", "passé simple"):
            "a formal/literary narration of a single completed past event — this tense is for written storytelling, not conversation",
        ("indicatif", "futur"):
            "a clear future-time marker (e.g. 'demain', 'l'année prochaine', 'bientôt')",
        ("conditionnel", "présent"):
            "a hypothetical, polite-request, or 'would' context — ideally paired with a 'si' clause",
        ("subjonctif", "présent"):
            "a clear subjunctive trigger in the main clause (e.g. 'il faut que', 'je veux que', 'bien que') describing a present/future wish, doubt, emotion, or necessity",
        ("subjonctif", "imparfait"):
            "a formal/literary context — this tense is rare in modern French, keep it formulaic (e.g. after 'bien que' in formal writing)",
    },
    Language.english: {
        ("indicative", "indicative present"):
            "a habitual/general-truth marker (e.g. 'every day', 'always') — not a specific past or future moment",
        ("indicative", "indicative present continuous"):
            "an action happening right now, or a definite near-future plan, with a clear 'right now' or scheduled-plan marker",
        ("indicative", "indicative past tense"):
            "a single, completed past event at a specific point in time (e.g. 'yesterday', 'last year') — not an ongoing state described with 'have/has'",
        ("indicative", "indicative present perfect"):
            "past relevance to the present or life experience (e.g. 'already', 'never', 'since', 'for five years') — not a specific, finished past time like 'yesterday'",
    },
}


def _disambiguation_hint(language: Language, mood: str, tense: str) -> str:
    hints = _DISAMBIGUATION_HINTS.get(language, {})
    return hints.get(
        (mood.lower(), canonical_tense(tense).lower()),
        "a context that makes this the only grammatically possible tense for the blank",
    )


async def pick_row(db: AsyncSession, language: Language, tenses: list[TenseFilter]) -> VerbConjugation | None:
    """A random personal form of a common verb in one of `tenses` (any tense if empty)."""
    query = select(VerbConjugation).where(
        VerbConjugation.language == language,
        VerbConjugation.person.in_(["1s", "2s", "3s", "1p", "2p", "3p"]),
    )
    common_verbs = COMMON_VERBS.get(language)
    if common_verbs:
        query = query.where(VerbConjugation.verb_infinitive.in_(common_verbs))
    if tenses:
        query = query.where(or_(*[
            and_(
                func.lower(VerbConjugation.mood) == t.mood.lower(),
                func.lower(VerbConjugation.tense).in_([v.lower() for v in variant_tense_names(t.tense)]),
            )
            for t in tenses
        ]))
    return (await db.execute(query.order_by(func.random()).limit(1))).scalar_one_or_none()


async def target_forms(db: AsyncSession, language: Language, row: VerbConjugation) -> tuple[str, list[str]]:
    """The form the blank stands for, plus any equally valid spellings."""
    correct_form = await resolve_compound_form(db, language, row.tense, row.person, row.form)

    # If this row is a "(1)"/"(2)" spelling-variant tense (e.g. Subjuntivo
    # pretérito imperfecto: hablara/hablase), also accept the sibling spelling.
    alternates: list[str] = []
    sibling_tense = _sibling_variant_tense(row.tense)
    if sibling_tense:
        sib_row = (await db.execute(
            select(VerbConjugation).where(
                VerbConjugation.language == language,
                VerbConjugation.verb_infinitive == row.verb_infinitive,
                VerbConjugation.mood == row.mood,
                func.lower(VerbConjugation.tense) == sibling_tense.lower(),
                VerbConjugation.person == row.person,
            )
        )).scalar_one_or_none()
        if sib_row:
            sib_form = await resolve_compound_form(db, language, sib_row.tense, sib_row.person, sib_row.form)
            if sib_form.lower() != correct_form.lower():
                alternates.append(sib_form)
    return correct_form, alternates


def build_sentence_messages(language: Language, row: VerbConjugation, correct_form: str) -> list[dict]:
    lang_name = LANGUAGE_NAMES[language]
    person_desc = PERSON_DESC.get(row.person, row.person)
    hint = _disambiguation_hint(language, row.mood, row.tense)
    pronoun = _PRIMARY_PRONOUN.get(language, {}).get(row.person, person_desc)
    return [
        {
            "role": "system",
            "content": "You are a language teacher. Respond with valid JSON only, no extra text.",
        },
        {
            "role": "user",
            "content": (
                f"Step 1: think of a natural {lang_name} sentence built around the word '{correct_form}' "
                f"(the verb '{row.verb_infinitive}', conjugated as {row.mood} — {row.tense}, {person_desc}). "
                f"'{correct_form}' must be the sentence's one and only main verb, in normal word order "
                f"(subject, then '{correct_form}', then the rest) — do not add any other conjugated verb "
                f"anywhere else in the sentence, and do not substitute a different verb in its place. In "
                f"particular, do NOT reach for a periphrasis like 'soler + infinitive' ('solía caminar', "
                f"'used to walk') as a workaround for conveying a habitual/ongoing meaning — express that "
                f"through the tense of '{correct_form}' itself and the context clue below, not a second verb. "
                f"Step 2: in that sentence, replace '{correct_form}' — and nothing else — with exactly "
                f"'___' (three underscores), with a normal space on both sides of it, exactly like every "
                f"other word boundary in the sentence. Do not attach '___' directly to another word or "
                f"to any leftover letters. "
                f"The sentence's subject MUST be '{pronoun}' — or, if you use a name or noun phrase "
                f"instead of the pronoun itself, it must be grammatically identical to '{pronoun}' "
                f"(e.g. a single named person for 'él/ella', or the speaker plus at least one other "
                f"person for 'nosotros'). Every other detail in the sentence — other pronouns, "
                f"possessives like 'my'/'mi', reflexive references — must also agree with '{pronoun}' "
                f"as the subject. Do not switch to a different grammatical person anywhere in the sentence. "
                f"The sentence MUST include {hint}. "
                f"A learner must be able to tell which tense is required just from reading the "
                f"sentence's context — do not write a sentence that would also make sense with a "
                f"different tense in the same blank. "
                f"If that context clue is an introductory clause (e.g. one starting with a word "
                f"meaning 'when'/'if'), it must come first, followed by a comma, and then the MAIN "
                f"clause — with '{correct_form}' as ITS verb, right after the subject, in normal word "
                f"order — must come second. Do not place '___' before the introductory clause; do not "
                f"write the main clause with a different verb while leaving '___' stranded elsewhere. "
                f"Return JSON with exactly these keys: "
                f'"sentence" (the sentence with ___), '
                f'"subject_hint" (the grammatical subject as it appears in the sentence, e.g. "je", "nous", "María").'
            ),
        },
    ]


async def generate_one(
    db: AsyncSession,
    language: Language,
    tenses: list[TenseFilter],
    client: LLMClient | None = None,
) -> SentenceExerciseItem | None:
    """One generation attempt: a validated item, or None if the LLM's output was unusable.

    Raises NoConjugationData if no verb matches `tenses`.
    """
    client = client or llm_client
    row = await pick_row(db, language, tenses)
    if row is None:
        raise NoConjugationData()
    correct_form, alternates = await target_forms(db, language, row)

    try:
        data = await client.chat_json(build_sentence_messages(language, row, correct_form), max_tokens=SENTENCE_MAX_TOKENS)
    except (json.JSONDecodeError, KeyError, httpx.HTTPStatusError, httpx.RequestError):
        return None
    if not isinstance(data, dict):
        return None
    sentence = str(data.get("sentence", "")).strip()
    subject_hint = str(data.get("subject_hint", "")).strip()
    if not _sentence_is_valid(sentence, subject_hint, correct_form, alternates, language, row.person):
        return None
    return SentenceExerciseItem(
        sentence=sentence,
        subject_hint=subject_hint,
        verb_infinitive=row.verb_infinitive,
        mood=row.mood,
        tense=canonical_tense(row.tense),
        person=row.person,
        correct_form=correct_form,
        alternates=alternates,
    )
