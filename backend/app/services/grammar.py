"""Grammar-correction exercises: one sentence with exactly one mistake to fix.

A small model is unreliable at making a mistake on purpose: it often hands back
a sentence that is still correct, or one with two mistakes. So exercises come
from three places, all levelled A1-C1 (ERROR_TYPES says where each mistake is taught):

- Bank: hand-written pairs in data/grammar/{language}.json, used more at the
  higher levels where the model is weakest.
- Rule-made (A1-A2): start from a correct sentence (a curated vocabulary
  example, or one the model writes) and the *server* inserts the mistake with
  a rule that is wrong by construction (la libro, a el, nosotros habla, an book).
- Model-made: for mistakes no rule can make (ser/estar, subjunctive, si-clauses…)
  the model writes the correct sentence and the broken copy, and the change
  must have the type's shape.

Generated exercises are only kept if they pass `verify`: the two sentences
differ by one small change, and two blind checks with the tuned conversation
CHECK_PROMPT agree — the correct sentence comes back unchanged, and the broken
one comes back as exactly the correct sentence. Shared by the grammar pool, the
exercises router (live fallback) and scripts/benchmark_llm.py --grammar.
"""
import functools
import json
import random
import re
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from pathlib import Path

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Language, VerbConjugation, VocabItem
from app.services.conversation import LEVELS, check_messages, fold
from app.services.exercise_gen import LANGUAGE_NAMES
from app.services.llm import LLMClient, llm_client

# Bump whenever a prompt, rule, check or the bank changes: stocked exercises made
# by an older version are never served and are purged on the next refill.
GRAMMAR_PROMPT_VERSION = 2
GRAMMAR_MAX_TOKENS = 250
CHECK_MAX_TOKENS = 200
MAX_CHANGED_WORDS = 3     # the mistake and its fix are each at most this many words
LIVE_ATTEMPTS = 10        # tries before a user waiting on a live exercise gets an error
# How often an exercise comes from the hand-written bank (data/grammar/*.json), by
# level: the model is weakest at the higher levels, where the bank matters most
BANK_SHARE = {1: 0.2, 2: 0.3, 3: 0.6, 4: 0.75, 5: 0.8}
# How often a rule-made exercise starts from a curated example rather than a model-written sentence
CURATED_SHARE = {1: 0.6, 2: 0.5, 3: 0.35, 4: 0.2, 5: 0.1}

TOPICS = [
    "daily routine", "food and cooking", "travel", "work", "family", "the weather", "school",
    "shopping", "hobbies", "health", "the city", "friends", "holidays", "home", "sport",
]


@dataclass(frozen=True)
class ErrorType:
    """A kind of mistake, and the CEFR level (1-5 = A1-C1) where it is taught.

    Rule-made types are made by a function in RULES. Model-made ones carry what
    to ask the model for (`describe`, with a worked `example`: wrong, right) and
    the `shape` the change must have (see shape_problem), and the `rule` shown
    as its explanation. Types with none of these only appear in the hand-written bank.
    """
    label: str
    level: int
    describe: str = ""
    example: tuple[str, str] = ("", "")
    shape: tuple = ()
    rule: str = ""  # model-made: the explanation shown (the model's own notes are often wrong)


def _words_shape(*words: str, insert: bool = False) -> tuple:
    """Every changed word is one of `words`; a swap on both sides unless `insert` (a word added or dropped)."""
    return ("words", frozenset(words), insert)


_EN_PREPOSITIONS = ("in", "on", "at", "to", "for", "of", "with", "by", "from", "about", "into", "onto",
                    "over", "under", "during", "since", "until", "the")
_SAME_VERB = ("same_verb",)  # the mistake is another form of the right verb (tense or mood)
# ("forms", wrong, right): same verb, and the fix brings in a form of `right` (mood or
# "mood/tense") that the mistake doesn't have, replacing one of `wrong` if given
_SUBJ_ES = ("forms", None, frozenset({"Subjuntivo"}))
_SUBJ_FR = ("forms", None, frozenset({"Subjonctif"}))
_SI_ES = ("forms", frozenset({"Condicional"}), frozenset({"Subjuntivo"}))
_SI_FR = ("forms", frozenset({"Conditionnel"}), frozenset({"Indicatif/Imparfait"}))
_PAST_EN = ("forms", None, frozenset({"indicative/indicative past tense"}))
_PARTICIPLE_EN = ("forms", None, frozenset({"indicative/indicative present perfect"}))  # stored as the participle

# Levels: Spanish A1-B1 follow the Lingua.com grammar syllabus (lingua.com/spanish/grammar),
# everything else the usual CEFR progression.
ERROR_TYPES: dict[Language, dict[str, ErrorType]] = {
    Language.spanish: {
        "article_gender": ErrorType("Article gender", 1),
        "contraction": ErrorType("Contraction", 1),
        "subject_verb": ErrorType("Subject–verb agreement", 1),
        "ser_estar": ErrorType(
            "ser vs estar", 1, "ser used where estar is needed, or estar where ser is needed",
            ("Mi hermano es cansado.", "Mi hermano está cansado."), ("verbs", frozenset({"ser", "estar"})),
            "Ser is for what something is (identity, profession, origin); estar is for states and location."),
        "gustar": ErrorType(
            "gustar agreement", 1, "gusta with a plural thing that is liked, or gustan with a singular one",
            ("Me gusta los tacos.", "Me gustan los tacos."),
            _words_shape("gusta", "gustan", "gustaba", "gustaban", "gustó", "gustaron", "gustaría", "gustarían"),
            "Gustar agrees with the thing that is liked: gusta + one thing, gustan + several."),
        "adjective_agreement": ErrorType(
            "Adjective agreement", 1, "an adjective that doesn't agree with its noun in gender or number",
            ("Las casas son blancos.", "Las casas son blancas."), ("ending",),
            "Adjectives agree with their noun in gender and number."),
        "muy_mucho": ErrorType(
            "muy vs mucho", 1, "muy and mucho/mucha/muchos/muchas swapped",
            ("Tengo muy hambre.", "Tengo mucha hambre."), _words_shape("muy", "mucho", "mucha", "muchos", "muchas"),
            "Muy goes with adjectives and adverbs; mucho/mucha/muchos/muchas go with nouns."),
        "a_en": ErrorType(
            "a vs en", 1, "a and en swapped (a is for going to a place, en for being in it)",
            ("Vivo a Madrid.", "Vivo en Madrid."), _words_shape("a", "al", "en", "el"),
            "A is for going to a place; en is for being in it."),
        "bien_bueno": ErrorType(
            "bien vs bueno, mal vs malo", 2, "the adverb bien/mal swapped with the adjective bueno/malo (or buen/mal)",
            ("Hablas español muy bueno.", "Hablas español muy bien."),
            _words_shape("bien", "bueno", "buena", "buenos", "buenas", "buen", "mal", "malo", "mala", "malos", "malas"),
            "Bien and mal say how something is done; bueno and malo describe a noun (buen and mal before a masculine singular noun)."),
        "preterite_form": ErrorType(
            "Irregular pretérito indefinido", 2,
            "an irregular verb in the pretérito indefinido given a made-up regular form",
            ("Ayer yo hací la cena.", "Ayer yo hice la cena."), ("made_up",),
            "This verb is irregular in the pretérito indefinido."),
        "poder_saber": ErrorType(
            "poder vs saber", 2, "poder used where saber is needed (a learned skill) or saber where poder is needed",
            ("No puedo nadar, nunca aprendí.", "No sé nadar, nunca aprendí."), ("verbs", frozenset({"poder", "saber"})),
            "Saber is for skills you have learned; poder is for being able or allowed to."),
        "object_pronoun": ErrorType(
            "Object pronoun", 2, "a wrong direct or indirect object pronoun (lo, la, los, las, le, les)",
            ("Las llaves, los tengo yo.", "Las llaves, las tengo yo."),
            _words_shape("lo", "la", "los", "las", "le", "les", "me", "te", "nos", "os", "se"),
            "Object pronouns agree with what they replace: lo/la/los/las for direct objects, le/les for indirect ones."),
        "por_para": ErrorType(
            "por vs para", 3, "por used where para is needed, or para where por is needed",
            ("Gracias para todo.", "Gracias por todo."), _words_shape("por", "para"),
            "Para is for purpose, destination and deadlines; por is for cause, exchange, duration and means."),
        "preterite_imperfect": ErrorType(
            "Indefinido vs imperfecto", 3,
            "the pretérito indefinido used where the imperfecto is needed, or the reverse",
            ("De niño, fui al parque cada día.", "De niño, iba al parque cada día."), _SAME_VERB,
            "The indefinido is for completed events; the imperfecto for habits, descriptions and background."),
        "subjunctive_wish": ErrorType(
            "Subjunctive after wishes", 3,
            "the indicative used instead of the subjunctive after a wish, request or advice (quiero que, te pido que, es importante que)",
            ("Quiero que vienes mañana.", "Quiero que vengas mañana."), _SUBJ_ES,
            "After a wish, request or advice about someone else (quiero que, te pido que, es importante que), use the subjunctive."),
        "cuando_future": ErrorType(
            "cuando + subjunctive", 3, "cuando + future instead of cuando + present subjunctive for a future action",
            ("Te escribo cuando llegaré.", "Te escribo cuando llegue."), _SUBJ_ES,
            "Cuando + a future action takes the present subjunctive, never the future."),
        "subjunctive_doubt": ErrorType(
            "Subjunctive after doubt or emotion", 4,
            "the indicative used instead of the subjunctive after doubt, emotion or a negated opinion (no creo que, dudo que, me alegra que)",
            ("No creo que es verdad.", "No creo que sea verdad."), _SUBJ_ES,
            "Doubt, emotion and negated opinions (dudo que, me alegra que, no creo que) take the subjunctive."),
        "subjunctive_conjunction": ErrorType(
            "Subjunctive after a conjunction", 4,
            "the indicative used instead of the subjunctive after antes de que, para que or sin que",
            ("Llámame antes de que sales.", "Llámame antes de que salgas."), _SUBJ_ES,
            "Antes de que, para que and sin que are always followed by the subjunctive."),
        "si_clause": ErrorType(
            "si-clause", 4, "si + conditional instead of si + imperfect subjunctive in an unreal condition",
            ("Si tendría tiempo, iría.", "Si tuviera tiempo, iría."), _SI_ES,
            "In an unreal condition, si takes the imperfect subjunctive (si tuviera), never the conditional."),
        "sequence_of_tenses": ErrorType(
            "Sequence of tenses", 5,
            "after a past verb (quería que, me pidió que) the indicative or conditional instead of the imperfect subjunctive",
            ("Me pidió que vendría.", "Me pidió que viniera."), _SUBJ_ES,
            "After a past verb of wishing, asking or feeling, the subjunctive moves into the past: the imperfect subjunctive."),
        "si_clause_past": ErrorType(
            "Unreal past (si-clause)", 5, "si + conditional perfect instead of si + pluperfect subjunctive for an unreal past",
            ("Si habría sabido, no iba.", "Si hubiera sabido, no iba."), _SI_ES,
            "For an unreal past condition, si takes the pluperfect subjunctive (si hubiera…), never the conditional."),
        "subjunctive_relative": ErrorType("Subjunctive in a relative clause", 4),
        "ojala": ErrorType("ojalá + subjunctive", 5),
        "relative_pronoun": ErrorType(
            "Relative pronoun", 5, "a wrong relative pronoun (que, quien, lo que, el que, la que, cuyo, donde)",
            ("No sé que quieres.", "No sé lo que quieres."),
            _words_shape("que", "quien", "quienes", "lo", "el", "la", "los", "las", "cual", "cuales",
                         "cuyo", "cuya", "cuyos", "cuyas", "donde", "su", "sus", insert=True),
            "Que refers to people or things; quien only to people (mostly after a preposition); lo que means 'what'; cuyo/cuya means 'whose'."),
    },
    Language.french: {
        "article_gender": ErrorType("Article gender", 1),
        "contraction": ErrorType("Contraction", 1),
        "subject_verb": ErrorType("Subject–verb agreement", 1),
        "adjective_agreement": ErrorType(
            "Adjective agreement", 1, "an adjective that doesn't agree with its noun in gender or number",
            ("Ma sœur est grand.", "Ma sœur est grande."), ("ending",),
            "Adjectives agree with their noun in gender and number."),
        "partitive": ErrorType(
            "Partitive article", 1, "a wrong partitive article (du, de la, de l', des)",
            ("Je bois de la thé.", "Je bois du thé."), ("partitive",),
            "The partitive agrees with the noun: du (masculine), de la (feminine), de l' (before a vowel), des (plural)."),
        "preposition_place": ErrorType(
            "à / en / au with places", 1, "à, en or au swapped before a city or a country",
            ("Il habite en Paris.", "Il habite à Paris."), _words_shape("à", "en", "au", "aux", "dans"),
            "Cities take à; feminine countries take en; masculine countries take au; plural countries take aux."),
        "avoir_expressions": ErrorType(
            "avoir faim, avoir froid…", 1, "être used instead of avoir in avoir faim, avoir soif, avoir froid, avoir chaud or avoir … ans",
            ("Je suis faim.", "J'ai faim."), ("verbs", frozenset({"avoir", "être"})),
            "Hunger, thirst, cold, heat and age use avoir: avoir faim, avoir froid, avoir vingt ans."),
        "auxiliary": ErrorType(
            "être vs avoir", 2, "avoir used instead of être as the auxiliary of the passé composé, or the reverse",
            ("Nous avons partis tôt.", "Nous sommes partis tôt."), ("verbs", frozenset({"avoir", "être"})),
            "Verbs of movement or change of state (aller, venir, partir, naître…) and reflexive verbs take être in the passé composé; the others take avoir."),
        "participle_agreement": ErrorType(
            "Participle agreement with être", 2, "a past participle after être that doesn't agree with the subject",
            ("Elle est allé au cinéma.", "Elle est allée au cinéma."), ("ending",),
            "With être, the past participle agrees with the subject in gender and number."),
        "negation_de": ErrorType(
            "de after a negation", 2, "du, de la, des, un or une kept after a negation instead of de",
            ("Je n'ai pas des frères.", "Je n'ai pas de frères."), ("partitive",),
            "After a negation, du, de la, des, un and une become de (d' before a vowel)."),
        "irregular_participle": ErrorType(
            "Irregular past participle", 2, "an irregular past participle given a made-up regular form (prendu, écrivé)",
            ("J'ai prendu le bus.", "J'ai pris le bus."), ("made_up",),
            "This verb has an irregular past participle."),
        "comparative": ErrorType(
            "Comparative", 2, "plus bon or plus bien instead of meilleur or mieux",
            ("Ce vin est plus bon.", "Ce vin est meilleur."),
            _words_shape("plus", "bon", "bonne", "bons", "bonnes", "bien", "meilleur", "meilleure",
                         "meilleurs", "meilleures", "mieux", "mal", "pire", "pires"),
            "Bon becomes meilleur and bien becomes mieux, never plus bon or plus bien."),
        "imparfait_pc": ErrorType(
            "Imparfait vs passé composé", 3, "the passé composé used where the imparfait is needed, or the reverse",
            ("Quand il a fait beau, on allait au parc.", "Quand il faisait beau, on allait au parc."), _SAME_VERB,
            "The passé composé is for completed events; the imparfait for habits, descriptions and background."),
        "subjunctive_wish": ErrorType(
            "Subjunctive after wishes", 3, "the indicative used instead of the subjunctive after il faut que or vouloir que",
            ("Il faut que tu viens.", "Il faut que tu viennes."), _SUBJ_FR,
            "Il faut que and vouloir que are followed by the subjunctive."),
        "pronoun_y_en": ErrorType("y vs en", 3),
        "depuis_pendant": ErrorType(
            "depuis vs pendant", 3, "pendant used where depuis is needed (an action still going on), or the reverse",
            ("J'apprends le français pendant deux ans.", "J'apprends le français depuis deux ans."),
            _words_shape("depuis", "pendant"),
            "Depuis + present is for something still going on; pendant is for a finished length of time."),
        "subjunctive_doubt": ErrorType(
            "Subjunctive after doubt or emotion", 4, "the indicative used instead of the subjunctive after doubt or emotion (je doute que, je suis content que)",
            ("Je doute qu'il vient.", "Je doute qu'il vienne."), _SUBJ_FR,
            "Doubt and emotion (je doute que, je suis content que) take the subjunctive."),
        "subjunctive_conjunction": ErrorType(
            "Subjunctive after a conjunction", 4, "the indicative used instead of the subjunctive after bien que, pour que or avant que",
            ("Bien qu'il est tard, je reste.", "Bien qu'il soit tard, je reste."), _SUBJ_FR,
            "Bien que, pour que, avant que and quoi que are always followed by the subjunctive."),
        "si_clause": ErrorType(
            "si-clause", 4, "si + conditionnel instead of si + imparfait",
            ("Si j'aurais le temps, je viendrais.", "Si j'avais le temps, je viendrais."), _SI_FR,
            "After si, use the imparfait, never the conditional: si j'avais…, je ferais…"),
        "indirect_question": ErrorType("Indirect question", 4),
        "participle_agreement_avoir": ErrorType(
            "Participle agreement with avoir", 5,
            "a past participle after avoir that doesn't agree with a direct object placed before it",
            ("La lettre que j'ai écrit est longue.", "La lettre que j'ai écrite est longue."), ("ending",),
            "With avoir, the past participle agrees with a direct object placed before the verb."),
        "relative_pronoun": ErrorType(
            "Relative pronoun", 5, "que used where dont, lequel or laquelle is needed",
            ("Le livre que je parle est ici.", "Le livre dont je parle est ici."),
            _words_shape("dont", "que", "qui", "où", "lequel", "laquelle", "lesquels", "lesquelles",
                         "duquel", "auquel", "quoi"),
            "Use dont with verbs built with de (parler de) and for 'whose'; lequel/laquelle after a preposition."),
        "si_clause_past": ErrorType(
            "Unreal past (si-clause)", 5, "si + conditionnel passé instead of si + plus-que-parfait",
            ("Si j'aurais su, je serais venu.", "Si j'avais su, je serais venu."), _SI_FR,
            "For an unreal past, si takes the plus-que-parfait (si j'avais su), never the conditional."),
        "subjunctive_past": ErrorType("Past subjunctive", 5),
        "apres_que": ErrorType("après que + indicative", 5),
    },
    Language.english: {
        "a_an": ErrorType("a / an", 1),
        "subject_verb": ErrorType("Subject–verb agreement", 1),
        "plural": ErrorType(
            "Plural noun", 1, "a singular noun where a plural is needed, like two book",
            ("I have two brother.", "I have two brothers."), ("plural",),
            "After a number above one, or words like these, those and many, nouns are plural."),
        "do_does": ErrorType(
            "do / does", 1, "do with he/she/it, or does with I/you/we/they",
            ("Do she like tea?", "Does she like tea?"), _words_shape("do", "does", "don't", "doesn't"),
            "He, she and it take does/doesn't; I, you, we and they take do/don't."),
        "irregular_past": ErrorType(
            "Irregular past tense", 2, "a regularised past tense of an irregular verb, like goed or buyed",
            ("I goed home early.", "I went home early."), ("made_up",),
            "This verb is irregular: its past simple doesn't end in -ed."),
        "preposition": ErrorType(
            "Preposition", 2, "a wrong preposition of time or place (in, on, at)",
            ("See you in Monday.", "See you on Monday."), _words_shape(*_EN_PREPOSITIONS),
            "Time and place: in for months, years and inside places; on for days and dates; at for clock times and points."),
        "comparative": ErrorType(
            "Comparative", 2, "a wrong comparative or superlative (more big, most good, gooder)",
            ("It is more cheap here.", "It is cheaper here."), ("comparative",),
            "Short adjectives add -er/-est, long ones use more/most; good → better/best, bad → worse/worst."),
        "present_perfect_past": ErrorType(
            "Present perfect vs past simple", 3,
            "the present perfect with a finished time (yesterday, last year), or the past simple/present with since or for",
            ("I have met her yesterday.", "I met her yesterday."), _SAME_VERB,
            "The past simple goes with a finished time (yesterday, last year); the present perfect with since, for and time up to now."),
        "future_clause": ErrorType(
            "Future after if / when", 3, "will after if or when for a future action",
            ("When I will finish, I'll call.", "When I finish, I'll call."), ("same_verb", "will"),
            "After if, when, as soon as and before, use the present for a future action, not will."),
        "gerund_infinitive": ErrorType(
            "-ing or to + infinitive", 3, "a gerund where to + infinitive is needed, or the reverse (enjoy doing, decide to do)",
            ("I enjoy to read.", "I enjoy reading."), _SAME_VERB,
            "Some verbs take -ing (enjoy, finish, avoid), others to + infinitive (decide, want, hope)."),
        "used_to": ErrorType("used to", 3),
        "second_conditional": ErrorType(
            "Second conditional", 4, "would in the if-clause of an unreal present condition",
            ("If I would have a car, I would drive.", "If I had a car, I would drive."), _PAST_EN,
            "In the if-clause of an unreal condition use the past simple, not would."),
        "wish": ErrorType(
            "wish + past", 4, "a present form after I wish instead of a past form",
            ("I wish I have a dog.", "I wish I had a dog."), _PAST_EN,
            "Wish about the present takes a past form: I wish I had, I wish I could."),
        "passive": ErrorType(
            "Passive", 4, "a wrong verb form in a passive instead of the past participle (is make, was build, is speaking)",
            ("The cake was make by Tom.", "The cake was made by Tom."), _PARTICIPLE_EN,
            "The passive is be + past participle."),
        "third_conditional": ErrorType(
            "Third conditional", 5, "would have in the if-clause of an unreal past condition",
            ("If I would have seen it, I would have told you.", "If I had seen it, I would have told you."), _PAST_EN,
            "For an unreal past condition use if + past perfect (if I had known), not would have."),
        "would_rather": ErrorType(
            "would rather / it's time + past", 5, "a present form after I'd rather you or it's (high) time instead of a past form",
            ("It's time we leave.", "It's time we left."), _PAST_EN,
            "I'd rather you … and it's time … take a past form for the present."),
        "linker": ErrorType("Linking words", 4),
        "modal_infinitive": ErrorType("Bare infinitive after modals", 4),
        "relative_pronoun": ErrorType("Relative pronoun", 5),
        "correlative": ErrorType("Fixed pairs (no sooner … than)", 5),
        "so_such": ErrorType("so vs such", 5),
    },
}

# error type → label, for exercises of any language (a key means the same thing everywhere)
ERROR_LABELS = {key: t.label for types in ERROR_TYPES.values() for key, t in types.items()}


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
    kind = ERROR_TYPES[language][error_type]
    wrong, right = kind.example
    return [
        {"role": "system", "content": f"You are a {lang} teacher writing grammar exercises. Respond with valid JSON only."},
        {"role": "user", "content": (
            f"Write one natural, grammatically correct {lang} sentence about {topic}, 6 to 16 words long, "
            f"for a learner at level {code}. {guidance}\n"
            f"Then copy it with exactly one mistake: {kind.describe}. Change nothing else.\n"
            f'For example (do not reuse it): "{wrong}" instead of "{right}"\n'
            'Reply with JSON: {"correct": "<the correct sentence>", "wrong": "<the same sentence with the one mistake>"}'
        )},
    ]


# ── Checks ───────────────────────────────────────────────────────────────────

_PARTITIVE_WORDS = {"du", "de", "des", "la", "le", "les", "un", "une", "pas", "plus"}
_COMPARATIVE_WORDS = {"more", "most", "better", "best", "worse", "worst", "than", "the"}


def _bare(word: str) -> str:
    """The word without an elided prefix: j'avais → avais, qu'il → il."""
    return word.rsplit("'", 1)[-1]


async def _forms_of(db: AsyncSession, language: Language, words: set[str]) -> dict[str, set[tuple[str, str, str]]]:
    """{word: {(verb, mood, tense)}} for every form it can be, elisions seen through (j'avais → avais)."""
    bare = {w: _bare(w) for w in words}
    rows = (await db.execute(
        select(func.lower(VerbConjugation.form), VerbConjugation.verb_infinitive,
               VerbConjugation.mood, VerbConjugation.tense).distinct()
        .where(VerbConjugation.language == language, func.lower(VerbConjugation.form).in_(set(bare.values())))
    )).all()
    by_form: dict[str, set[tuple[str, str, str]]] = {}
    for form, verb, mood, tense in rows:
        by_form.setdefault(form, set()).add((verb, mood, tense))
    return {w: by_form[b] for w, b in bare.items() if b in by_form}


async def _verbs_of(db: AsyncSession, language: Language, words: set[str], finite: bool = True) -> dict[str, set[str]]:
    """{word: the verbs it is a form of} — personal forms only unless finite=False (participles too)."""
    forms = await _forms_of(db, language, words)
    verbs = {w: {v for v, mood, _ in f if not finite or mood in _FINITE_MOODS} for w, f in forms.items()}
    return {w: v for w, v in verbs.items() if v}


def _matches(form: tuple[str, str, str], specs: frozenset[str]) -> bool:
    _, mood, tense = form
    return mood in specs or f"{mood}/{tense}" in specs


async def shape_problem(db: AsyncSession, language: Language, error_type: str, correct: str, with_error: str) -> str | None:
    """Whether a model-made change really is the kind of mistake it was asked for.

    The model mislabels its own mistakes (a verb-ending slip sold as "adjective
    agreement", "tu arrive" — already a subjunctive — sold as a missing
    subjunctive), which would teach the wrong rule, so each type has a shape.
    """
    a, b = _words(with_error), _words(correct)
    if (change := _one_change(a, b)) is None:
        return "not exactly one small change"
    i1, i2, j1, j2 = change
    wrong, right = a[i1:i2], b[j1:j2]
    one_word = len(wrong) == len(right) == 1
    w, r = (wrong[0], right[0]) if one_word else ("", "")
    kind, *params = ERROR_TYPES[language][error_type].shape or ("none",)
    if kind == "words":
        allowed, insert = params
        ok = set(wrong) | set(right) <= allowed and (insert or bool(wrong and right))
    elif kind == "verbs":  # e.g. a form of ser in place of a form of estar
        verbs = await _verbs_of(db, language, set(wrong + right))
        pair = params[0]
        used = {v for x in wrong for v in verbs.get(x, set()) & pair}
        needed = {v for x in right for v in verbs.get(x, set()) & pair}
        ok = len(used) == len(needed) == 1 and used != needed
    elif kind in ("same_verb", "forms"):  # another tense or mood of the right verb
        forms = await _forms_of(db, language, set(wrong + right))
        wrong_forms = set().union(*(forms.get(x, set()) for x in wrong))
        right_forms = set().union(*(forms.get(x, set()) for x in right))
        ok = bool({f[0] for f in wrong_forms} & {f[0] for f in right_forms})
        if kind == "same_verb" and params:  # a word the mistake must contain ("will")
            ok = ok and params[0] in wrong
        if kind == "forms":
            needs_wrong, needs_right = params
            ok = (ok and any(_matches(f, needs_right) for f in right_forms)
                  and not any(_matches(f, needs_right) for f in wrong_forms)
                  and (needs_wrong is None or any(_matches(f, needs_wrong) for f in wrong_forms)))
    elif kind == "made_up":  # a regularised form that isn't a word: hací, goed, prendu
        verbs = await _verbs_of(db, language, {w, r}, finite=False) if one_word else {}
        ok = one_word and w not in verbs and r in verbs
    elif kind == "ending":  # the same adjective or participle with another ending, never a personal verb form
        stem = len(_common_prefix(w, r))
        ok = one_word and stem >= 3 and stem >= min(len(w), len(r)) - 2 and not await _verbs_of(db, language, {w, r})
    elif kind == "partitive":
        ok = all(x in _PARTITIVE_WORDS or x.startswith(("l'", "d'")) for x in wrong + right)
    elif kind == "plural":
        ok = one_word and len(r) > len(w) and len(_common_prefix(w, r)) >= len(w) - 1
    elif kind == "comparative":
        changed = wrong + right
        ok = bool(set(changed) & _COMPARATIVE_WORDS) or any(x.endswith(("er", "est")) for x in changed)
    else:
        ok = False  # a type the model isn't asked for
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
    source: str  # "rule" | "model" | "bank"

    def content(self) -> dict:
        """The Exercise.content stored and sent to the browser."""
        return {**asdict(self), "error_label": ERROR_LABELS.get(self.error_type, "")}


BANK_DIR = Path(__file__).resolve().parents[2] / "data" / "grammar"


@dataclass(frozen=True)
class BankItem:
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


def bank_exercise(language: Language, level: int, rng: random.Random) -> GrammarItem | None:
    items = [b for b in load_bank(language) if b.level == level]
    if not items:
        return None
    b = rng.choice(items)
    return GrammarItem(b.wrong, b.correct, b.type, b.why, "bank")


def choose_type(language: Language, level: int, rng: random.Random) -> str:
    """A mistake type to generate at `level`: mostly that level's, sometimes the one below."""
    types = ERROR_TYPES[language]
    makeable = {k: t for k, t in types.items() if k in RULES[language] or t.describe}
    weights = {k: 3 if t.level == level else 1 for k, t in makeable.items() if t.level in (level, level - 1)}
    if not weights:  # nothing taught at this level: the highest level below it
        top = max(t.level for t in makeable.values() if t.level <= level)
        weights = {k: 1 for k, t in makeable.items() if t.level == top}
    keys = sorted(weights)
    return rng.choices(keys, weights=[weights[k] for k in keys])[0]


async def curated_sentence(db: AsyncSession, language: Language, level: int, rng: random.Random) -> str | None:
    """A hand-written example sentence from the vocabulary data, at or below `level`."""
    examples = (await db.execute(
        select(VocabItem.example).where(
            VocabItem.language == language, VocabItem.owner_id.is_(None), VocabItem.level <= max(level, 1),
        )
    )).scalars().all()
    return rng.choice(examples) if examples else None


async def _rule_made(db, language, level, client, rng, curated_share: float, first: str | None = None) -> tuple[GrammarItem | None, str]:
    rules = RULES[language]
    order = [k for k in rules if k != first]
    rng.shuffle(order)
    if first in rules:
        order.insert(0, first)
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


async def _model_made(db, language, level, client, rng, error_type: str) -> tuple[GrammarItem | None, str]:
    data = await _ask(client, model_messages(language, level, rng.choice(TOPICS), error_type),
                      max_tokens=GRAMMAR_MAX_TOKENS)
    if data is None:
        return None, "not JSON"
    correct, wrong = (" ".join(str(data.get(k) or "").split()) for k in ("correct", "wrong"))
    if _words(correct) == _words(ERROR_TYPES[language][error_type].example[1]):
        return None, "copied the example"
    if problem := pair_problem(correct, wrong) or await shape_problem(db, language, error_type, correct, wrong):
        return None, problem
    problem, _ = await verify(client, language, level, correct, wrong)
    if problem:
        return None, problem
    # The shape check guarantees the type, so its rule is the right explanation;
    # the model's own notes are often wrong (or about another rule)
    return GrammarItem(wrong, correct, error_type, ERROR_TYPES[language][error_type].rule, "model"), "ok"


async def generate_one(
    db: AsyncSession, language: Language, level: int,
    client: LLMClient | None = None, rng: random.Random | None = None, live: bool = False,
) -> tuple[GrammarItem | None, str]:
    """One attempt: (exercise, "ok") or (None, why it was rejected). Raises LLMUnavailable.

    Some exercises come straight from the hand-written bank (more at higher
    levels); the rest are made for a mistake type taught at `level`, by a rule
    or by the model. live=True is for a user waiting: the bank if it has this
    level, else rule-made from a curated example (two LLM calls, likeliest to pass).
    """
    client = client or llm_client
    rng = rng or random.Random()
    if live or rng.random() < BANK_SHARE.get(level, 0):
        if item := bank_exercise(language, level, rng):
            return item, "ok"
    try:
        if live:
            return await _rule_made(db, language, level, client, rng, curated_share=1.0)
        error_type = choose_type(language, level, rng)
        if error_type in RULES[language]:
            return await _rule_made(db, language, level, client, rng, CURATED_SHARE.get(level, 0.3), first=error_type)
        return await _model_made(db, language, level, client, rng, error_type)
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
