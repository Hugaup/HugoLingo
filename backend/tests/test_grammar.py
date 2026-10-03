import random
import re

import httpx
import pytest
from sqlalchemy import func, select

from app.models import Exercise, ExerciseType, GrammarPoolItem, Language, VerbConjugation
from app.services import grammar, grammar_pool
from app.services.grammar import GRAMMAR_PROMPT_VERSION, Fix, GrammarItem, find_fix, grade_answer, pair_problem
from tests.conftest import PERSONS, TestSession

ES, FR, EN = Language.spanish, Language.french, Language.english


class FakeLLM:
    """Answers the grammar prompts.

    The checker either agrees with the exercise (returns the first sentence it
    was asked about — verify always checks the correct sentence first — for
    both checks), finds nothing wrong anywhere ("blind"), or corrects
    everything to a fixed sentence ("stubborn").
    """
    model = "fake-llm"

    def __init__(self, checker="agree", written="Tengo un libro nuevo en casa.", pair=None, why="Checker says so."):
        self.checker = checker
        self.written = written
        self.pair = pair
        self.why = why
        self.calls = 0
        self._first = None

    async def chat_json(self, messages, max_tokens=None, temperature=None):
        self.calls += 1
        system, prompt = messages[0]["content"], messages[1]["content"]
        if system.startswith("You check one message"):
            sentence = re.search(r'The learner replied: "(.*)"$', prompt, re.S).group(1)
            if self.checker == "blind":
                return {"corrected": sentence, "explanation": ""}
            if self.checker == "stubborn":
                return {"corrected": "Algo completamente distinto aquí.", "explanation": "?"}
            if self._first is None or sentence == self._first:
                self._first = sentence
                return {"corrected": sentence, "explanation": ""}
            first, self._first = self._first, None
            return {"corrected": first, "explanation": self.why}
        if "writing grammar exercises" in system:
            return self.pair
        if system.startswith("You write example sentences"):
            return {"sentence": self.written}
        raise AssertionError(f"unexpected prompt: {system}")


class DownLLM:
    model = "down"

    async def chat_json(self, messages, **kwargs):
        raise httpx.ConnectError("refused")


async def add_verbs(db, language, verbs):
    db.add_all(
        VerbConjugation(language=language, verb_infinitive=verb, mood=mood, tense=tense, person=p, form=f)
        for (verb, mood, tense), forms in verbs.items()
        for p, f in zip(PERSONS, forms)
    )
    await db.commit()


# ── The one change between two sentences ─────────────────────────────────────

def test_find_fix_lays_out_a_one_word_correction():
    assert find_fix("Tengo una libro nuevo.", "Tengo un libro nuevo.") == Fix(
        wrong="una", right="un", before="Tengo ", after=" libro nuevo.")


def test_find_fix_handles_contractions_missing_and_extra_words():
    assert find_fix("Voy a el cine.", "Voy al cine.") == Fix("a el", "al", "Voy ", " cine.")
    assert find_fix("I want go home.", "I want to go home.") == Fix("", "to", "I want ", " go home.")
    assert find_fix("I go to home.", "I go home.") == Fix("to", "", "I go ", "home.")
    assert find_fix("I am here too.", "I am here.") == Fix("too", "", "I am here ", ".")


@pytest.mark.parametrize("with_error,corrected", [
    ("Tengo un libro.", "Tengo un libro."),        # the reported bug: nothing wrong to fix
    ("tengo un libro", "Tengo un libro."),         # only capitals/punctuation differ
    ("Tengo una libro y un casa.", "Tengo un libro y una casa."),  # two mistakes
    ("A b c d e f.", "G h i j k l."),              # a rewrite, not a correction
])
def test_find_fix_needs_exactly_one_small_change(with_error, corrected):
    assert find_fix(with_error, corrected) is None


def test_pair_problem_rejects_unusable_pairs():
    assert pair_problem("Tengo un libro nuevo.", "Tengo un libro nuevo.") == "not exactly one small change"
    assert pair_problem("Un libro.", "Una libro.") == "too short"
    assert pair_problem("Tengo un libro nuevo", "Tengo una libro nuevo") == "not a full sentence"
    assert pair_problem("Tengo un libro nuevo.", "Tengo una libro nuevo.") is None


# ── Rule-made mistakes ───────────────────────────────────────────────────────

async def test_article_gender_uses_the_nouns_known_gender(db, vocab):
    rng = random.Random(1)
    made = await grammar.article_gender(db, ES, "Tengo un libro nuevo en la mesa.", rng)
    assert made.with_error in {"Tengo una libro nuevo en la mesa.", "Tengo un libro nuevo en el mesa."}
    assert made.error_type == "article_gender"

    made = await grammar.article_gender(db, FR, "La maison est grande.", rng)
    assert made.with_error == "Le maison est grande."  # capital kept
    assert made.explanation == "'maison' is feminine: la maison, une maison."


async def test_article_gender_skips_nouns_whose_article_doesnt_show_gender(db, vocab):
    rng = random.Random(1)
    assert await grammar.article_gender(db, ES, "El agua está muy fría hoy.", rng) is None
    assert await grammar.article_gender(db, ES, "El estudiante lee mucho.", rng) is None  # la estudiante is fine
    assert await grammar.article_gender(db, FR, "Le médecin arrive bientôt.", rng) is None
    # a la playa → a el playa would also need "al": two mistakes
    assert await grammar.article_gender(db, ES, "Vamos a la playa mañana.", rng) is None


async def test_contraction_expands_al_del_au_du_but_not_des(db):
    rng = random.Random(1)
    made = await grammar.contraction(db, ES, "Al final vamos al cine.", rng)
    assert made.with_error in {"A el final vamos al cine.", "Al final vamos a el cine."}
    made = await grammar.contraction(db, FR, "Je mange du pain.", rng)
    assert (made.with_error, made.explanation) == ("Je mange de le pain.", "'de le' always contracts to 'du'.")
    assert await grammar.contraction(db, FR, "Je mange des pommes.", rng) is None


async def test_subject_verb_swaps_in_another_persons_form(db, spanish_verbs):
    for seed in range(5):
        made = await grammar.subject_verb(db, ES, "Nosotros hablamos español en casa.", random.Random(seed))
        verb = made.with_error.split()[1]
        assert verb in {"hablo", "hablas", "habla", "habláis", "hablan", "hablé", "hablaste", "habló",
                        "hablasteis", "hablaron"}
        assert made.explanation == f"The verb must agree with 'nosotros': hablamos, not {verb}."


async def test_subject_verb_never_swaps_in_a_form_right_for_the_subject(db, spanish_verbs):
    # tenía is 1s and 3s: "yo tenía" must never become "yo tenía" or another yo form
    for seed in range(8):
        made = await grammar.subject_verb(db, ES, "Yo tenía mucho trabajo ayer.", random.Random(seed))
        assert made.with_error.split()[1] in {"tenías", "teníamos", "teníais", "tenían"}
    made = await grammar.subject_verb(db, ES, "Yo no te hablo nunca más.", random.Random(0))
    assert made.with_error.startswith("Yo no te ") and made.with_error.split()[3] != "hablo"


async def test_subject_verb_avoids_swaps_an_accent_away_from_a_right_form(db, spanish_verbs):
    # "ella hablo" could be fixed to habla or habló, so hablo is never used for ella
    for seed in range(10):
        made = await grammar.subject_verb(db, ES, "Ella habla con su madre.", random.Random(seed))
        assert made.with_error.split()[1] in {"hablas", "hablamos", "habláis", "hablan"}


@pytest.mark.parametrize("sentence", [
    "Hablamos español todos los días.",   # no written subject: another person is often still correct
    "Siempre como con ella en casa.",     # after a preposition, ella is not the subject
])
async def test_subject_verb_needs_a_written_subject_starting_a_clause(db, spanish_verbs, sentence):
    assert await grammar.subject_verb(db, ES, sentence, random.Random(0)) is None


async def test_subject_verb_skips_forms_needing_elision_and_english_modals(db):
    await add_verbs(db, FR, {("aller", "Indicatif", "Présent"): ["vais", "vas", "va", "allons", "allez", "vont"]})
    await add_verbs(db, EN, {("will", "indicative", "indicative present"): ["will", "will", "wills", "will", "will", "will"]})
    for seed in range(6):
        made = await grammar.subject_verb(db, FR, "Je vais au marché demain.", random.Random(seed))
        assert made.with_error.split()[1] in {"vas", "va", "vont"}  # never "je allons"
    assert await grammar.subject_verb(db, EN, "You will go home soon.", random.Random(0)) is None


async def test_a_an(db):
    rng = random.Random(0)
    made = await grammar.a_an(db, EN, "She eats an apple every day.", rng)
    assert (made.with_error, made.explanation) == ("She eats a apple every day.", "Use 'an' before a vowel sound: an apple.")
    made = await grammar.a_an(db, EN, "He has a car now.", rng)
    assert made.with_error == "He has an car now."
    assert await grammar.a_an(db, EN, "He waited a hour at a BBC office.", rng) is None  # h- and acronyms skipped


# ── Checks ───────────────────────────────────────────────────────────────────

async def test_verify_keeps_a_pair_the_checker_agrees_with():
    problem, why = await grammar.verify(FakeLLM(), ES, 2, "Tengo un libro nuevo.", "Tengo una libro nuevo.")
    assert (problem, why) == (None, "Checker says so.")


async def test_verify_rejects_a_mistake_the_checker_cannot_find():
    """The reported bug: the "sentence with a mistake" was already correct."""
    problem, _ = await grammar.verify(FakeLLM("blind"), ES, 2, "Tengo un libro nuevo.", "Tengo una libro nuevo.")
    assert problem == "checker fixed it differently"


async def test_verify_rejects_a_correct_sentence_the_checker_would_change():
    problem, _ = await grammar.verify(FakeLLM("stubborn"), ES, 2, "Tengo un libro nuevo.", "Tengo una libro nuevo.")
    assert problem == "checker changed the correct sentence"


async def test_verify_rejects_identical_sentences_without_asking_the_model():
    llm = FakeLLM()
    problem, _ = await grammar.verify(llm, ES, 2, "Tengo un libro nuevo.", "Tengo un libro nuevo.")
    assert problem == "not exactly one small change" and llm.calls == 0


SER_ESTAR = {
    ("ser", "Indicativo", "Indicativo presente"): ["soy", "eres", "es", "somos", "sois", "son"],
    ("estar", "Indicativo", "Indicativo presente"): ["estoy", "estás", "está", "estamos", "estáis", "están"],
}


@pytest.mark.parametrize("error_type,correct,wrong,ok", [
    ("por_para", "Este regalo es para ti.", "Este regalo es por ti.", True),
    ("por_para", "Este regalo es para ti.", "Este regalo es a ti.", False),
    ("ser_estar", "Mi madre está cansada hoy.", "Mi madre es cansada hoy.", True),
    ("ser_estar", "Mi madre está cansada hoy.", "Mi madre estás cansada hoy.", False),
    ("preposition", "Voy al colegio cada día.", "Voy en el colegio cada día.", True),
    ("preposition", "Voy al colegio cada día.", "Voy al colegios cada día.", False),
    ("adjective_agreement", "La casa es muy blanca.", "La casa es muy blanco.", True),
    # a verb-ending slip the model labelled as adjective agreement
    ("adjective_agreement", "Ella come una manzana.", "Ella comes una manzana.", False),
])
async def test_model_made_mistakes_must_match_their_type(db, spanish_verbs, error_type, correct, wrong, ok):
    await add_verbs(db, ES, SER_ESTAR)
    problem = await grammar.shape_problem(db, ES, error_type, correct, wrong)
    assert (problem is None) == ok


# ── Making exercises ─────────────────────────────────────────────────────────

async def test_rule_made_from_a_curated_example(db, vocab, monkeypatch):
    monkeypatch.setattr(grammar, "MODEL_MADE_SHARE", 0)
    monkeypatch.setattr(grammar, "CURATED_SHARE", {2: 1.0})
    llm = FakeLLM()
    for seed in range(10):
        item, reason = await grammar.generate_one(db, ES, 2, llm, random.Random(seed))
        if item:
            break
    assert reason == "ok" and item.source == "rule"
    assert find_fix(item.sentence_with_error, item.corrected_sentence) is not None
    assert item.content()["error_label"] == grammar.ERROR_LABELS[item.error_type]


async def test_rule_made_from_a_written_sentence(db, vocab, monkeypatch):
    monkeypatch.setattr(grammar, "MODEL_MADE_SHARE", 0)
    monkeypatch.setattr(grammar, "CURATED_SHARE", {})
    monkeypatch.setattr(grammar, "RULES", {ES: {"article_gender": grammar.article_gender}})
    item, reason = await grammar.generate_one(db, ES, 2, FakeLLM(written="Tengo un libro nuevo en casa."), random.Random(0))
    assert reason == "ok"
    assert (item.sentence_with_error, item.corrected_sentence) == ("Tengo una libro nuevo en casa.", "Tengo un libro nuevo en casa.")
    assert item.explanation == "'libro' is masculine: el libro, un libro."


async def test_model_made_prefers_the_checkers_explanation(db, monkeypatch):
    monkeypatch.setattr(grammar, "MODEL_MADE_SHARE", 1)
    monkeypatch.setattr(grammar, "MODEL_ERRORS", {ES: {"por_para": "por/para"}})
    pair = {"correct": "Este regalo es para ti.", "wrong": "Este regalo es por ti.", "explanation": "Generator's note."}
    item, reason = await grammar.generate_one(db, ES, 2, FakeLLM(pair=pair, why="Para marks who receives it."), random.Random(0))
    assert reason == "ok"
    assert (item.error_type, item.source, item.explanation) == ("por_para", "model", "Para marks who receives it.")


async def test_model_made_rejects_an_unchanged_sentence(db, monkeypatch):
    monkeypatch.setattr(grammar, "MODEL_MADE_SHARE", 1)
    pair = {"correct": "Este regalo es para ti.", "wrong": "Este regalo es para ti.", "explanation": "?"}
    item, reason = await grammar.generate_one(db, ES, 2, FakeLLM(pair=pair), random.Random(0))
    assert item is None and reason == "not exactly one small change"


async def test_live_generation_is_rule_made_from_curated_examples(db, vocab, monkeypatch):
    monkeypatch.setattr(grammar, "MODEL_MADE_SHARE", 1)  # ignored when live
    asked = []
    llm = FakeLLM()
    real = llm.chat_json

    async def spy(messages, **kwargs):
        asked.append(messages[0]["content"])
        return await real(messages, **kwargs)
    llm.chat_json = spy
    item = await grammar.generate_live(db, ES, 2, llm, random.Random(0))
    assert item.source == "rule"
    assert all(system.startswith("You check one message") for system in asked)  # no writing call


async def test_generate_one_reports_ollama_down(db):
    with pytest.raises(grammar.LLMUnavailable):
        for seed in range(5):  # whichever path it takes, the first LLM call fails
            await grammar.generate_one(db, EN, 2, DownLLM(), random.Random(seed))


# ── Grading ──────────────────────────────────────────────────────────────────

CONTENT = {
    "sentence_with_error": "Tengo una libro nuevo.",
    "corrected_sentence": "Tengo un libro nuevo.",
    "explanation": "'libro' is masculine: el libro, un libro.",
}


@pytest.mark.parametrize("answer", ["Tengo un libro nuevo.", "tengo un libro nuevo", "  Tengo   un libro nuevo !"])
def test_grading_ignores_capitals_punctuation_and_spacing(answer):
    graded = grade_answer(CONTENT, answer)
    assert graded.result == "correct" and graded.fix.right == "un"


def test_grading_accents_only_is_almost():
    content = {"sentence_with_error": "El esta aqui.", "corrected_sentence": "Él está aquí.", "explanation": ""}
    assert grade_answer(content, "El esta aqui").result == "almost"


@pytest.mark.parametrize("answer,note", [
    ("Tengo una libro nuevo.", "The mistake is still there: una → un."),
    ("Tengo un libro viejo.", "You fixed the mistake (una → un), but changed something else too."),
    ("Tengo una libro nueva.", "The mistake was: una → un."),
])
def test_grading_says_what_went_wrong(answer, note):
    graded = grade_answer(CONTENT, answer)
    assert graded.result == "wrong"
    assert graded.explanation == f"{note} 'libro' is masculine: el libro, un libro."


def test_grading_an_older_exercise_without_one_clear_change():
    graded = grade_answer({"corrected_sentence": "Je mange des pommes."}, "Je mange des pomme.")
    assert (graded.result, graded.fix) == ("wrong", None)
    assert graded.explanation == "The corrected sentence is: 'Je mange des pommes.'."


# ── The stock ────────────────────────────────────────────────────────────────

def pool_row(**overrides):
    values = dict(
        language=ES, level=2, sentence_with_error="Tengo una libro nuevo.", corrected_sentence="Tengo un libro nuevo.",
        error_type="article_gender", explanation="Masculine.", source="rule", model="test",
        prompt_version=GRAMMAR_PROMPT_VERSION,
    )
    return GrammarPoolItem(**(values | overrides))


async def count_pool(db):
    return await db.scalar(select(func.count()).select_from(GrammarPoolItem))


async def test_take_prefers_the_requested_level_and_removes_it(db):
    db.add_all([pool_row(level=1, explanation="Level 1."), pool_row(level=3, explanation="Level 3.")])
    await db.commit()
    assert (await grammar_pool.take(db, ES, 3)).explanation == "Level 3."
    assert await count_pool(db) == 1
    # another level still beats a wait; an empty stock gives nothing
    assert (await grammar_pool.take(db, ES, 5)).explanation == "Level 1."
    assert await grammar_pool.take(db, ES, 5) is None
    assert await grammar_pool.take(db, FR, 1) is None


async def test_take_never_serves_an_older_version(db):
    db.add(pool_row(prompt_version=GRAMMAR_PROMPT_VERSION - 1))
    await db.commit()
    assert await grammar_pool.take(db, ES, 2) is None


async def test_refill_tops_up_and_purges_old_versions(db, vocab, monkeypatch):
    monkeypatch.setattr(grammar, "MODEL_MADE_SHARE", 0)
    monkeypatch.setattr(grammar, "CURATED_SHARE", {})
    monkeypatch.setattr(grammar, "RULES", {ES: {"article_gender": grammar.article_gender}})
    db.add(pool_row(prompt_version=GRAMMAR_PROMPT_VERSION - 1))
    await db.commit()
    added = await grammar_pool.refill(ES, target=3, session_factory=TestSession, client=FakeLLM(),
                                      rng=random.Random(0), wait_while_busy=False)
    assert added == 3
    rows = (await db.execute(select(GrammarPoolItem))).scalars().all()
    assert {r.prompt_version for r in rows} == {GRAMMAR_PROMPT_VERSION}
    assert {r.model for r in rows} == {"fake-llm"}


async def test_refill_stops_when_ollama_is_down(db):
    added = await grammar_pool.refill(EN, target=3, session_factory=TestSession, client=DownLLM(),
                                      rng=random.Random(0), wait_while_busy=False)
    assert added == 0


# ── API ──────────────────────────────────────────────────────────────────────

async def test_generate_serves_from_the_stock_without_the_llm(logged_in, db, monkeypatch):
    async def no_live(*args, **kwargs):
        raise AssertionError("should not generate live")
    monkeypatch.setattr(grammar, "generate_live", no_live)
    db.add(pool_row())
    await db.commit()
    alice, _ = await logged_in()
    r = await alice.post("/exercises/generate", json={"type": "grammar", "language": "spanish", "difficulty": 2})
    assert r.status_code == 200
    content = r.json()["content"]
    assert content["sentence_with_error"] == "Tengo una libro nuevo."
    assert content["error_label"] == "Article gender"
    assert await count_pool(db) == 0


async def test_generate_falls_back_to_live_then_gives_up_kindly(logged_in, monkeypatch):
    alice, _ = await logged_in()
    made = GrammarItem("Voy a el cine.", "Voy al cine.", "contraction", "'a el' always contracts to 'al'.", "rule")

    async def live(*args, **kwargs):
        return made
    monkeypatch.setattr(grammar, "generate_live", live)
    r = await alice.post("/exercises/generate", json={"type": "grammar", "language": "spanish", "difficulty": 2})
    assert r.json()["content"]["corrected_sentence"] == "Voy al cine."

    async def nothing(*args, **kwargs):
        return None
    monkeypatch.setattr(grammar, "generate_live", nothing)
    r = await alice.post("/exercises/generate", json={"type": "grammar", "language": "spanish", "difficulty": 2})
    assert r.status_code == 502 and "try again" in r.json()["detail"]


async def test_generate_rejects_unsupported_languages(logged_in):
    alice, _ = await logged_in()
    r = await alice.post("/exercises/generate", json={"type": "grammar", "language": "norwegian", "difficulty": 2})
    assert r.status_code == 400


async def test_check_returns_the_fix_and_is_lenient(logged_in, db):
    alice, _ = await logged_in()
    exercise = Exercise(type=ExerciseType.grammar, language=ES, difficulty=2, content=CONTENT)
    db.add(exercise)
    await db.commit()

    data = (await alice.post("/exercises/check", json={"exercise_id": exercise.id, "user_answer": "tengo un libro nuevo"})).json()
    assert (data["is_correct"], data["almost"]) == (True, False)
    assert data["fix"] == {"wrong": "una", "right": "un", "before": "Tengo ", "after": " libro nuevo."}

    data = (await alice.post("/exercises/check", json={"exercise_id": exercise.id, "user_answer": "Tengo una libro nuevo."})).json()
    assert data["is_correct"] is False
    assert data["explanation"].startswith("The mistake is still there: una → un.")
