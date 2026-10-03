"""Grammar-correction exercises: one sentence with exactly one mistake to fix.

A small model is unreliable at making a mistake on purpose: it often hands back
a sentence that is still correct, or one with two mistakes. So exercises are
made in two ways:

- Rule-made: start from a correct sentence (a curated vocabulary example, or
  one the model writes) and the *server* inserts the mistake with a rule that
  is wrong by construction (la libro, a el, nosotros habla, an book).
- Model-made: for mistakes no rule can make (ser/estar, por/para, être/avoir…)
  the model writes the correct sentence and the broken copy.

Either way an exercise is only kept if it passes `verify`: the two sentences
differ by one small change, and two blind checks with the tuned conversation
CHECK_PROMPT agree — the correct sentence comes back unchanged, and the broken
one comes back as exactly the correct sentence. Shared by the grammar pool, the
exercises router (live fallback) and scripts/benchmark_llm.py --grammar.
"""
import json
import random
import re
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Language, VerbConjugation, VocabItem
from app.services.conversation import LEVELS, check_messages, fold
from app.services.exercise_gen import LANGUAGE_NAMES
from app.services.llm import LLMClient, llm_client

# Bump whenever a prompt, rule or check changes: stocked exercises made by an
# older version are never served and are purged on the next refill.
GRAMMAR_PROMPT_VERSION = 1
GRAMMAR_MAX_TOKENS = 250
CHECK_MAX_TOKENS = 200
MAX_CHANGED_WORDS = 3     # the mistake and its fix are each at most this many words
LIVE_ATTEMPTS = 10        # tries before a user waiting on a live exercise gets an error
MODEL_MADE_SHARE = 0.35   # the rest are rule-made
# How often a rule-made exercise starts from a curated example rather than a model-written sentence
CURATED_SHARE = {1: 0.6, 2: 0.5, 3: 0.35, 4: 0.2, 5: 0.1}

TOPICS = [
    "daily routine", "food and cooking", "travel", "work", "family", "the weather", "school",
    "shopping", "hobbies", "health", "the city", "friends", "holidays", "home", "sport",
]

ERROR_LABELS = {
    # rule-made
    "article_gender": "Article gender",
    "contraction": "Contraction",
    "subject_verb": "Subject–verb agreement",
    "a_an": "a / an",
    # model-made
    "ser_estar": "ser vs estar",
    "por_para": "por vs para",
    "gustar": "gustar agreement",
    "auxiliary": "être vs avoir",
    "partitive": "Partitive article",
    "adjective_agreement": "Adjective agreement",
    "preposition": "Preposition",
    "irregular_past": "Irregular past tense",
    "plural": "Plural noun",
    "do_does": "do / does",
}

# Mistakes the model makes (and the checks then confirm), as described to it
MODEL_ERRORS: dict[Language, dict[str, str]] = {
    Language.spanish: {
        "ser_estar": "ser used where estar is needed, or estar where ser is needed",
        "por_para": "por used where para is needed, or para where por is needed",
        "gustar": "gusta with a plural thing that is liked, or gustan with a singular one",
        "adjective_agreement": "an adjective that doesn't agree with its noun in gender or number",
        "preposition": "a wrong preposition",
    },
    Language.french: {
        "auxiliary": "avoir used instead of être as the auxiliary of the passé composé, or the reverse",
        "partitive": "a wrong partitive article (du, de la, de l', des, or de after a negation)",
        "adjective_agreement": "an adjective that doesn't agree with its noun in gender or number",
        "preposition": "a wrong preposition",
    },
    Language.english: {
        "irregular_past": "a regularised past tense of an irregular verb, like goed or buyed",
        "plural": "a singular noun where a plural is needed, like two book",
        "do_does": "do with he/she/it, or does with I/you/we/they",
        "preposition": "a wrong preposition",
    },
}


class LLMUnavailable(Exception):
    """Ollama couldn't be reached (as opposed to giving an unusable answer)."""


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
    return (i1, i2, j1, j2) if max(i2 - i1, j2 - j1) <= MAX_CHANGED_WORDS else None


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


# ── Rule-made mistakes ───────────────────────────────────────────────────────

@dataclass(frozen=True)
class Injected:
    with_error: str
    error_type: str
    explanation: str


def _replace(sentence: str, token: Token, new: str) -> str:
    """Swap one word, keeping a leading capital."""
    if sentence[token.start:token.start + 1].isupper():
        new = new[:1].upper() + new[1:]
    return sentence[:token.start] + new + sentence[token.end:]


# (definite, indefinite) article per gender
ARTICLES = {
    Language.spanish: {"m": ("el", "un"), "f": ("la", "una")},
    Language.french: {"m": ("le", "un"), "f": ("la", "une")},
}
# Nouns whose article doesn't show their gender (el agua is feminine) or that take
# either article: mar, radio, and people of either sex (la estudiante, la médecin)
GENDER_EXCEPTIONS = {
    Language.spanish: {"agua", "hambre", "alma", "águila", "aula", "arma", "hacha", "área", "ala", "hada",
                       "azúcar", "mar", "arte", "radio", "orden", "bebé", "estudiante", "joven", "policía",
                       "guía", "artista", "turista", "periodista", "dentista", "taxista", "cantante",
                       "cliente", "paciente", "agente", "colega", "testigo", "modelo"},
    Language.french: {"médecin", "professeur", "élève", "enfant", "collègue", "secrétaire", "touriste",
                      "artiste", "journaliste", "dentiste", "ministre", "juge", "guide", "camarade",
                      "adulte", "architecte", "photographe", "pianiste", "bébé"},
}
# a/de + el contract to al/del: switching to the masculine article there would make two mistakes
_CONTRACTING_PREPOSITIONS = {Language.spanish: {"a", "de"}, Language.french: {"à", "de"}}


async def noun_genders(db: AsyncSession, language: Language) -> dict[str, str]:
    """Curated nouns whose article shows their gender: {"libro": "m", "casa": "f", …}."""
    if language not in ARTICLES:
        return {}
    gender_of = {article: g for g, pair in ARTICLES[language].items() for article in pair}
    rows = (await db.execute(
        select(VocabItem.text, VocabItem.article).where(
            VocabItem.language == language, VocabItem.owner_id.is_(None), VocabItem.pos == "noun",
        )
    )).all()
    return {
        text.lower(): gender_of[article] for text, article in rows
        if article in gender_of and " " not in text and text.lower() not in GENDER_EXCEPTIONS[language]
    }


async def article_gender(db: AsyncSession, language: Language, sentence: str, rng: random.Random) -> Injected | None:
    """el libro → la libro: give a known noun the article of the other gender."""
    if language not in ARTICLES:
        return None
    nouns = await noun_genders(db, language)
    gender_of = {article: g for g, pair in ARTICLES[language].items() for article in pair}
    toks = tokens(sentence)
    options = []
    for i in range(len(toks) - 1):
        article, noun = toks[i].word, toks[i + 1].word
        gender = nouns.get(noun)
        if gender is None or gender_of.get(article) != gender:
            continue
        other = "f" if gender == "m" else "m"
        new = ARTICLES[language][other][ARTICLES[language][gender].index(article)]
        if new == ARTICLES[language]["m"][0] and i > 0 and toks[i - 1].word in _CONTRACTING_PREPOSITIONS[language]:
            continue
        options.append((toks[i], new, noun, gender))
    if not options:
        return None
    token, new, noun, gender = rng.choice(options)
    definite, indefinite = ARTICLES[language][gender]
    kind = "masculine" if gender == "m" else "feminine"
    return Injected(_replace(sentence, token, new), "article_gender",
                    f"'{noun}' is {kind}: {definite} {noun}, {indefinite} {noun}.")


CONTRACTIONS = {
    Language.spanish: {"al": "a el", "del": "de el"},
    # not "des": it's usually the plural indefinite article, not de + les
    Language.french: {"au": "à le", "aux": "à les", "du": "de le"},
}


async def contraction(db: AsyncSession, language: Language, sentence: str, rng: random.Random) -> Injected | None:
    """al → a el, au → à le."""
    table = CONTRACTIONS.get(language, {})
    options = [t for t in tokens(sentence) if t.word in table]
    if not options:
        return None
    token = rng.choice(options)
    expanded = table[token.word]
    return Injected(_replace(sentence, token, expanded), "contraction",
                    f"'{expanded}' always contracts to '{token.word}'.")


# Subject pronoun → the persons its verb can take
SUBJECTS = {
    Language.spanish: {
        "yo": ["1s"], "tú": ["2s"], "él": ["3s"], "ella": ["3s"], "usted": ["3s"],
        "nosotros": ["1p"], "nosotras": ["1p"], "vosotros": ["2p"], "vosotras": ["2p"],
        "ellos": ["3p"], "ellas": ["3p"], "ustedes": ["3p"],
    },
    Language.french: {
        "je": ["1s"], "tu": ["2s"], "il": ["3s"], "elle": ["3s"], "on": ["3s"],
        "nous": ["1p"], "vous": ["2p"], "ils": ["3p"], "elles": ["3p"],
    },
    Language.english: {
        "i": ["1s"], "you": ["2s", "2p"], "he": ["3s"], "she": ["3s"], "it": ["3s"],
        "we": ["1p"], "they": ["3p"],
    },
}
# Words that may sit between a subject and its verb (no, ne, object pronouns)
_BETWEEN = {
    Language.spanish: {"no", "me", "te", "se", "nos", "os", "lo", "la", "le", "les", "los", "las"},
    Language.french: {"ne", "me", "te", "se", "le", "la", "les", "lui", "leur", "y", "en", "nous", "vous"},
    Language.english: set(),
}
# A pronoun only counts as the subject at the start of a clause: after a
# preposition or a verb it's an object (con ella, I told you)
_CLAUSE_STARTS = {
    Language.spanish: {"y", "pero", "que", "cuando", "porque", "si", "aunque", "mientras", "donde", "o", "pues"},
    Language.french: {"et", "mais", "que", "quand", "si", "où", "ou", "puis", "car", "lorsque"},
    Language.english: {"and", "but", "that", "when", "because", "if", "while", "so", "or", "where", "then"},
}
# Verbs nobody gets wrong this way (*he wills go*): modals conjugate like verbs in the data
_SKIP_VERBS = {Language.english: {"will", "can", "may", "must", "shall", "might", "could", "would", "should"}}
# Moods whose forms belong to a subject (imperatives and infinitives don't)
_FINITE_MOODS = {"Indicativo", "Subjuntivo", "Condicional", "Indicatif", "Subjonctif", "Conditionnel", "indicative"}


async def subject_verb(db: AsyncSession, language: Language, sentence: str, rng: random.Random) -> Injected | None:
    """nosotros hablamos → nosotros habla: the same verb and tense, another person's form.

    Only with a written subject pronoun: without one (Spanish/French often drop
    it) the other person's form is usually a correct sentence too.
    """
    subjects = SUBJECTS.get(language)
    if not subjects:
        return None
    toks = tokens(sentence)
    pairs = []  # (subject token, verb token)
    for i, t in enumerate(toks):
        if t.word not in subjects:
            continue
        if i > 0 and toks[i - 1].word not in _CLAUSE_STARTS[language] and "," not in sentence[toks[i - 1].end:t.start]:
            continue
        j = i + 1
        while j < len(toks) and j - i <= 2 and toks[j].word in _BETWEEN[language]:
            j += 1
        if j < len(toks):
            pairs.append((t, toks[j]))
    if not pairs:
        return None

    rows = (await db.execute(
        select(VerbConjugation.verb_infinitive, VerbConjugation.mood, VerbConjugation.tense,
               VerbConjugation.person, func.lower(VerbConjugation.form))
        .where(VerbConjugation.language == language,
               VerbConjugation.mood.in_(_FINITE_MOODS),
               func.lower(VerbConjugation.form).in_({verb.word for _, verb in pairs}))
    )).all()
    rng.shuffle(pairs)
    for subject, verb in pairs:
        persons = subjects[subject.word]
        if verb.word in _SKIP_VERBS.get(language, set()):
            continue
        matches = [r for r in rows if r[4] == verb.word and r.person in persons]
        if not matches:
            continue
        row = rng.choice(matches)
        forms = (await db.execute(
            select(VerbConjugation.mood, VerbConjugation.tense, VerbConjugation.person,
                   func.lower(VerbConjugation.form))
            .where(VerbConjugation.language == language,
                   VerbConjugation.verb_infinitive == row.verb_infinitive,
                   VerbConjugation.mood.in_(_FINITE_MOODS))
        )).all()
        # Never swap in a form that is right for this subject in some other tense, even
        # give or take an accent: "ella viajo" could be fixed to viaja or viajó
        right_for_subject = {fold(f) for _, _, p, f in forms if p in persons}
        swaps = sorted({
            f for m, t, p, f in forms
            if (m, t) == (row.mood, row.tense) and p not in persons and fold(f) not in right_for_subject and " " not in f
            and not (subject.word == "je" and f[0] in "aeiouhéèêâîôû")  # "je allons" would also need j'
        })
        if not swaps:
            continue
        new = rng.choice(swaps)
        written = "I" if subject.word == "i" else subject.word
        return Injected(_replace(sentence, verb, new), "subject_verb",
                        f"The verb must agree with '{written}': {sentence[verb.start:verb.end]}, not {new}.")
    return None


_CONSONANTS = set("bcdfgjklmnpqrstvwxyz")  # no h: "an hour"


async def a_an(db: AsyncSession, language: Language, sentence: str, rng: random.Random) -> Injected | None:
    """an apple → a apple, a book → an book."""
    if language != Language.english:
        return None
    toks = tokens(sentence)
    options = []
    for article, noun in zip(toks, toks[1:]):
        word = sentence[noun.start:noun.end]
        if article.word == "an":
            options.append((article, "a", f"Use 'an' before a vowel sound: an {word}."))
        elif article.word == "a" and word[0] in _CONSONANTS:  # lowercase only: skips acronyms (a BBC film)
            options.append((article, "an", f"Use 'a' before a consonant sound: a {word}."))
    if not options:
        return None
    token, new, why = rng.choice(options)
    return Injected(_replace(sentence, token, new), "a_an", why)


RULES = {
    Language.spanish: {"article_gender": article_gender, "contraction": contraction, "subject_verb": subject_verb},
    Language.french: {"article_gender": article_gender, "contraction": contraction, "subject_verb": subject_verb},
    Language.english: {"a_an": a_an, "subject_verb": subject_verb},
}
LANGUAGES = list(RULES)


def supports(language: Language) -> bool:
    return language in RULES


# ── Prompts ──────────────────────────────────────────────────────────────────

def _level(level: int) -> tuple[str, str]:
    return LEVELS.get(level, LEVELS[2])


def writing_messages(language: Language, level: int, topic: str, hint: str) -> list[dict]:
    """Ask for one correct sentence that a rule can then break."""
    lang = LANGUAGE_NAMES[language]
    code, guidance = _level(level)
    return [
        {"role": "system", "content": f"You write example sentences for people learning {lang}. Respond with valid JSON only."},
        {"role": "user", "content": (
            f"Write one natural, grammatically correct {lang} sentence about {topic}, 6 to 14 words long, "
            f"for a learner at level {code}. {guidance}\n"
            f"{hint}\n"
            'Reply with JSON: {"sentence": "<the sentence>"}'
        )},
    ]


async def _writing_hint(db: AsyncSession, language: Language, rule: str, rng: random.Random) -> str:
    """What the model's sentence must contain for `rule` to be able to break it."""
    if rule == "article_gender":
        nouns = await noun_genders(db, language)
        if nouns:
            noun = rng.choice(sorted(nouns))
            definite, indefinite = ARTICLES[language][nouns[noun]]
            return f'Use the noun "{noun}" in the singular, with "{definite}" or "{indefinite}" directly before it.'
    if rule == "contraction":
        options = " or ".join(f'"{c}"' for c in CONTRACTIONS[language])
        return f"Use {options}."
    if rule == "subject_verb":
        # je is left out: before a vowel it becomes j', which the rule can't use
        pronoun = rng.choice([p for p in SUBJECTS[language] if p != "je"])
        pronoun = "I" if pronoun == "i" else pronoun
        return f'Start the sentence with the subject pronoun "{pronoun}", directly followed by its verb.'
    if rule == "a_an":
        return 'Use "a" or "an" before a noun.'
    return ""


def model_messages(language: Language, level: int, topic: str, error_type: str) -> list[dict]:
    """Ask for a correct sentence and a copy with one mistake of `error_type`."""
    lang = LANGUAGE_NAMES[language]
    code, guidance = _level(level)
    return [
        {"role": "system", "content": f"You are a {lang} teacher writing grammar exercises. Respond with valid JSON only."},
        {"role": "user", "content": (
            f"Write one natural, grammatically correct {lang} sentence about {topic}, 6 to 14 words long, "
            f"for a learner at level {code}. {guidance}\n"
            f"Then copy it with exactly one mistake: {MODEL_ERRORS[language][error_type]}. Change nothing else.\n"
            'Reply with JSON: {"correct": "<the correct sentence>", "wrong": "<the same sentence with the one mistake>", '
            '"explanation": "<one short sentence in English giving the rule>"}'
        )},
    ]


# ── Checks ───────────────────────────────────────────────────────────────────

# Words a "preposition" mistake may change (prepositions, with the articles they contract with)
_PREPOSITION_WORDS = {
    Language.spanish: {"a", "al", "ante", "bajo", "con", "contra", "de", "del", "desde", "en", "entre", "hacia",
                       "hasta", "para", "por", "según", "sin", "sobre", "tras", "el", "la", "los", "las"},
    Language.french: {"à", "au", "aux", "de", "du", "des", "dans", "en", "sur", "sous", "chez", "pour", "par",
                      "avec", "sans", "vers", "entre", "depuis", "pendant", "le", "la", "les"},
    Language.english: {"in", "on", "at", "to", "for", "of", "with", "by", "from", "about", "into", "onto",
                       "over", "under", "during", "since", "until", "the"},
}
_PARTITIVE_WORDS = {"du", "de", "des", "la", "le", "les", "un", "une"}
_DO_WORDS = {"do", "does", "don't", "doesn't"}
# Model-made mistakes whose changed words must be forms of one verb and of the other
_VERB_PAIRS = {"ser_estar": {"ser", "estar"}, "auxiliary": {"avoir", "être"}}


async def _verbs_of(db: AsyncSession, language: Language, words: set[str]) -> dict[str, set[str]]:
    """{word: the verbs it is a personal form of}."""
    rows = (await db.execute(
        select(func.lower(VerbConjugation.form), VerbConjugation.verb_infinitive).distinct()
        .where(VerbConjugation.language == language, VerbConjugation.mood.in_(_FINITE_MOODS),
               func.lower(VerbConjugation.form).in_(words))
    )).all()
    verbs: dict[str, set[str]] = {}
    for form, verb in rows:
        verbs.setdefault(form, set()).add(verb)
    return verbs


async def shape_problem(db: AsyncSession, language: Language, error_type: str, correct: str, with_error: str) -> str | None:
    """Whether a model-made change really is the kind of mistake it was asked for.

    The model mislabels its own mistakes (a verb-ending slip sold as "adjective
    agreement"), which would teach the wrong rule, so each type has a shape.
    """
    a, b = _words(with_error), _words(correct)
    i1, i2, j1, j2 = _one_change(a, b)
    wrong, right = a[i1:i2], b[j1:j2]
    one_word = len(wrong) == len(right) == 1
    w, r = (wrong[0], right[0]) if one_word else ("", "")
    ok = True
    if error_type in _VERB_PAIRS:
        verbs = await _verbs_of(db, language, {w, r}) if one_word else {}
        pair = _VERB_PAIRS[error_type]
        ok = one_word and any(
            {vw, vr} == pair for vw in verbs.get(w, set()) & pair for vr in verbs.get(r, set()) & pair
        )
    elif error_type == "por_para":
        ok = {w, r} == {"por", "para"}
    elif error_type == "gustar":
        ok = one_word and w.startswith("gust") and r.startswith("gust")
    elif error_type == "do_does":
        ok = one_word and {w, r} <= _DO_WORDS
    elif error_type == "preposition":
        ok = set(wrong) | set(right) <= _PREPOSITION_WORDS[language]
    elif error_type == "partitive":
        ok = all(x in _PARTITIVE_WORDS or x.startswith(("l'", "d'")) for x in wrong + right)
    elif error_type == "adjective_agreement":
        # the same adjective with another ending (blanco/blanca), never a verb form
        stem = len(_common_prefix(w, r))
        ok = one_word and stem >= 3 and stem >= min(len(w), len(r)) - 2 and not await _verbs_of(db, language, {w, r})
    elif error_type == "plural":
        ok = one_word and len(r) > len(w) and len(_common_prefix(w, r)) >= len(w) - 1
    elif error_type == "irregular_past":
        verbs = await _verbs_of(db, language, {w, r}) if one_word else {}
        ok = one_word and w.endswith("ed") and w not in verbs and r in verbs
    return None if ok else f"not a {error_type} mistake"


def _common_prefix(a: str, b: str) -> str:
    n = 0
    while n < min(len(a), len(b)) and a[n] == b[n]:
        n += 1
    return a[:n]


def pair_problem(correct: str, with_error: str) -> str | None:
    """Why two sentences can't make an exercise (before asking the checker), or None."""
    if not correct or not with_error or max(len(correct), len(with_error)) > 300:
        return "missing or too long"
    if len(tokens(correct)) < 4:
        return "too short"
    if not correct.rstrip(" \"'»”’").endswith((".", "!", "?")):
        return "not a full sentence"
    if find_fix(with_error, correct) is None:
        return "not exactly one small change"  # incl. a "mistake" identical to the correct sentence
    return None


async def _ask(client: LLMClient, messages: list[dict], **kwargs) -> dict | None:
    """The model's JSON object, or None if it wasn't one. Connection errors propagate."""
    try:
        data = await client.chat_json(messages, **kwargs)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


async def check_sentence(client: LLMClient, language: Language, level: int, sentence: str) -> tuple[str | None, str]:
    """What the tuned conversation checker corrects `sentence` to, and its explanation."""
    data = await _ask(client, check_messages(language, level, None, sentence),
                      max_tokens=CHECK_MAX_TOKENS, temperature=0)
    corrected = data.get("corrected") if data else None
    why = data.get("explanation") if data else None
    return (corrected if isinstance(corrected, str) and corrected.strip() else None,
            why.strip() if isinstance(why, str) else "")


async def verify(client: LLMClient, language: Language, level: int, correct: str, with_error: str) -> tuple[str | None, str]:
    """(why this pair isn't a trustworthy exercise or None, the checker's explanation of the mistake)."""
    if problem := pair_problem(correct, with_error):
        return problem, ""
    fixed, _ = await check_sentence(client, language, level, correct)
    if fixed is None or _words(fixed) != _words(correct):
        return "checker changed the correct sentence", ""
    fixed, why = await check_sentence(client, language, level, with_error)
    if fixed is None or _words(fixed) != _words(correct):
        return "checker fixed it differently", ""  # incl. finding no mistake at all
    return None, why


# ── Making one exercise ──────────────────────────────────────────────────────

@dataclass(frozen=True)
class GrammarItem:
    sentence_with_error: str
    corrected_sentence: str
    error_type: str
    explanation: str
    source: str  # "rule" | "model"

    def content(self) -> dict:
        """The Exercise.content stored and sent to the browser."""
        return {**asdict(self), "error_label": ERROR_LABELS.get(self.error_type, "")}


async def curated_sentence(db: AsyncSession, language: Language, level: int, rng: random.Random) -> str | None:
    """A hand-written example sentence from the vocabulary data, at or below `level`."""
    examples = (await db.execute(
        select(VocabItem.example).where(
            VocabItem.language == language, VocabItem.owner_id.is_(None), VocabItem.level <= max(level, 1),
        )
    )).scalars().all()
    return rng.choice(examples) if examples else None


async def _rule_made(db, language, level, client, rng, curated_share: float) -> tuple[GrammarItem | None, str]:
    rules = RULES[language]
    order = list(rules)
    rng.shuffle(order)
    correct = None
    if rng.random() < curated_share:
        correct = await curated_sentence(db, language, level, rng)
    if correct is None:
        hint = await _writing_hint(db, language, order[0], rng)
        data = await _ask(client, writing_messages(language, level, rng.choice(TOPICS), hint),
                          max_tokens=GRAMMAR_MAX_TOKENS)
        correct = data.get("sentence") if data else None
        if not isinstance(correct, str):
            return None, "not JSON"
    correct = " ".join(correct.split())
    for key in order:
        if injected := await rules[key](db, language, correct, rng):
            break
    else:
        return None, "no rule applies"
    problem, _ = await verify(client, language, level, correct, injected.with_error)
    if problem:
        return None, problem
    return GrammarItem(injected.with_error, correct, injected.error_type, injected.explanation, "rule"), "ok"


async def _model_made(db, language, level, client, rng) -> tuple[GrammarItem | None, str]:
    error_type = rng.choice(sorted(MODEL_ERRORS[language]))
    data = await _ask(client, model_messages(language, level, rng.choice(TOPICS), error_type),
                      max_tokens=GRAMMAR_MAX_TOKENS)
    if data is None:
        return None, "not JSON"
    correct, wrong, why = (" ".join(str(data.get(k) or "").split()) for k in ("correct", "wrong", "explanation"))
    if problem := pair_problem(correct, wrong) or await shape_problem(db, language, error_type, correct, wrong):
        return None, problem
    problem, checker_why = await verify(client, language, level, correct, wrong)
    if problem:
        return None, problem
    # The checker explains the mistake it actually found; the generator's note was
    # written before the mistake and is often off
    explanation = (checker_why or why)[:500]
    if not explanation:
        return None, "no explanation"
    return GrammarItem(wrong, correct, error_type, explanation, "model"), "ok"


async def generate_one(
    db: AsyncSession, language: Language, level: int,
    client: LLMClient | None = None, rng: random.Random | None = None, live: bool = False,
) -> tuple[GrammarItem | None, str]:
    """One attempt: (exercise, "ok") or (None, why it was rejected). Raises LLMUnavailable.

    live=True is for a user waiting: rule-made from a curated example where
    there is one (two LLM calls, and the likeliest to pass), never model-made.
    """
    client = client or llm_client
    rng = rng or random.Random()
    try:
        if not live and rng.random() < MODEL_MADE_SHARE:
            return await _model_made(db, language, level, client, rng)
        curated_share = 1.0 if live else CURATED_SHARE.get(level, 0.3)
        return await _rule_made(db, language, level, client, rng, curated_share)
    except (httpx.HTTPStatusError, httpx.RequestError) as e:
        raise LLMUnavailable(str(e)) from e


async def generate_live(
    db: AsyncSession, language: Language, level: int,
    client: LLMClient | None = None, rng: random.Random | None = None,
) -> GrammarItem | None:
    """For a user waiting on an empty stock: a few attempts, then give up (None)."""
    for _ in range(LIVE_ATTEMPTS):
        item, _reason = await generate_one(db, language, level, client, rng, live=True)
        if item:
            return item
    return None


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


def grade_answer(content: dict, answer: str) -> GrammarGrade:
    """Grade a typed correction. Capitals, punctuation and spacing never count;
    an accent-only difference is "almost" (still a mistake)."""
    corrected = str(content.get("corrected_sentence", ""))
    with_error = str(content.get("sentence_with_error", ""))
    explanation = str(content.get("explanation", "")).strip()
    fix = find_fix(with_error, corrected) if with_error else None
    given, expected = _words(answer), _words(corrected)

    if given and given == expected:
        return GrammarGrade("correct", explanation, fix)
    if given and [fold(w) for w in given] == [fold(w) for w in expected]:
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
