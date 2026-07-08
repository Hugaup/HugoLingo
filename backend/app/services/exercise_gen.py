import json
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.models import ExerciseType, Language, VerbConjugation
from app.services.llm import llm_client
from app.services.conjugation_utils import FORM_ALTERNATES

LANGUAGE_NAMES = {
    Language.french: "French",
    Language.spanish: "Spanish",
    Language.english: "English",
    Language.norwegian: "Norwegian Bokmål",
    Language.galician: "Galician",
}

DIFFICULTY_LABELS = {1: "A1", 2: "A2", 3: "B1", 4: "B2", 5: "C1"}

TENSES_BY_DIFFICULTY = {
    1: ["present tense"],
    2: ["present tense", "simple past"],
    3: ["present tense", "simple past", "future tense", "imperfect"],
    4: ["present tense", "simple past", "future tense", "imperfect", "subjunctive present", "conditional"],
    5: ["any tense including subjunctive past, pluperfect, conditional perfect"],
}


async def generate_conjugation(language: Language, difficulty: int) -> dict:
    lang = LANGUAGE_NAMES[language]
    level = DIFFICULTY_LABELS.get(difficulty, "B1")
    tenses = ", ".join(TENSES_BY_DIFFICULTY.get(difficulty, ["present tense"]))

    messages = [
        {
            "role": "system",
            "content": (
                "You are a language teacher. Always respond with valid JSON only, no extra text."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Create a {lang} verb conjugation exercise at level {level}. "
                f"The exercise must require one of these tenses: {tenses}. "
                "Write a natural sentence where the verb is replaced by '___'. "
                "Return a JSON object with exactly these keys: "
                '"sentence" (the sentence with ___), '
                '"verb_infinitive" (the infinitive of the missing verb), '
                '"correct_answer" (the correctly conjugated form), '
                '"tense" (name of the tense used), '
                '"subject" (grammatical subject of the verb), '
                '"explanation" (1-2 sentences explaining why this conjugation is correct).'
            ),
        },
    ]

    return await _fetch_with_retry(messages)


async def generate_grammar(language: Language, difficulty: int) -> dict:
    lang = LANGUAGE_NAMES[language]
    level = DIFFICULTY_LABELS.get(difficulty, "B1")

    messages = [
        {
            "role": "system",
            "content": "You are a language teacher. Always respond with valid JSON only, no extra text.",
        },
        {
            "role": "user",
            "content": (
                f"Create a {lang} grammar correction exercise at level {level}. "
                "Write a sentence that contains exactly one grammar error (agreement, gender, preposition, article, etc). "
                "Return a JSON object with exactly these keys: "
                '"sentence_with_error" (the sentence containing the error), '
                '"corrected_sentence" (the fully corrected sentence), '
                '"error_type" (short label, e.g. "gender agreement"), '
                '"wrong_word" (the incorrect word or phrase), '
                '"correct_word" (the correct replacement), '
                '"explanation" (1-2 sentences explaining the rule).'
            ),
        },
    ]

    return await _fetch_with_retry(messages)


async def generate_reading(language: Language, difficulty: int) -> dict:
    lang = LANGUAGE_NAMES[language]
    level = DIFFICULTY_LABELS.get(difficulty, "B1")

    messages = [
        {
            "role": "system",
            "content": "You are a language teacher. Always respond with valid JSON only, no extra text.",
        },
        {
            "role": "user",
            "content": (
                f"Create a {lang} reading comprehension exercise at level {level}. "
                "Write a short paragraph (4-6 sentences) followed by 2 comprehension questions. "
                "Return a JSON object with exactly these keys: "
                '"passage" (the reading text), '
                '"questions" (array of 2 objects, each with "question" and "correct_answer" keys).'
            ),
        },
    ]

    return await _fetch_with_retry(messages)


async def _fetch_with_retry(messages: list[dict], retries: int = 2) -> dict:
    last_error = None
    for _ in range(retries + 1):
        try:
            return await llm_client.chat_json(messages)
        except (json.JSONDecodeError, KeyError) as e:
            last_error = e
        except (httpx.HTTPStatusError, httpx.RequestError) as e:
            raise ValueError(f"LLM unavailable — ensure Ollama is running ({e})")
    raise ValueError(f"LLM returned invalid JSON after {retries + 1} attempts: {last_error}")


GENERATORS = {
    ExerciseType.conjugation: generate_conjugation,
    ExerciseType.grammar: generate_grammar,
    ExerciseType.reading: generate_reading,
}


async def generate_exercise(ex_type: ExerciseType, language: Language, difficulty: int) -> dict:
    generator = GENERATORS[ex_type]
    return await generator(language, difficulty)


async def check_conjugation(
    content: dict,
    user_answer: str,
    db: AsyncSession | None = None,
    language: Language | None = None,
) -> tuple[bool, str]:
    correct = content.get("correct_answer", "").strip().lower()
    given = user_answer.strip().lower()
    explanation = content.get("explanation", "")

    if correct == given:
        return True, explanation

    # Secondary check: accept if the user's answer is any valid form of the verb in the DB
    if db is not None and language is not None:
        verb = content.get("verb_infinitive", "").strip()
        if verb:
            result = await db.execute(
                select(VerbConjugation.form).where(
                    VerbConjugation.language == language,
                    func.lower(VerbConjugation.verb_infinitive) == verb.lower(),
                    func.lower(VerbConjugation.form) == given,
                ).limit(1)
            )
            if result.scalar_one_or_none() is not None:
                return True, explanation

    if given in FORM_ALTERNATES.get(correct, []) or correct in FORM_ALTERNATES.get(given, []):
        return True, explanation

    return False, f"The correct answer is '{content['correct_answer']}'. " + explanation


def check_grammar(content: dict, user_answer: str) -> tuple[bool, str]:
    correct = content.get("corrected_sentence", "").strip().lower()
    given = user_answer.strip().lower()
    is_correct = correct == given
    explanation = content.get("explanation", "")
    if not is_correct:
        explanation = f"The corrected sentence is: '{content['corrected_sentence']}'. " + explanation
    return is_correct, explanation


def check_reading(content: dict, user_answer: str, question_index: int = 0) -> tuple[bool, str]:
    questions = content.get("questions", [])
    if not questions:
        return False, "No questions found."
    q = questions[min(question_index, len(questions) - 1)]
    correct = q.get("correct_answer", "").strip().lower()
    given = user_answer.strip().lower()
    is_correct = correct in given or given in correct
    if is_correct:
        explanation = f"Correct! The answer is: {q['correct_answer']}"
    else:
        explanation = f"The expected answer was: '{q['correct_answer']}'"
    return is_correct, explanation


CHECKERS = {
    ExerciseType.grammar: check_grammar,
    ExerciseType.reading: check_reading,
}
