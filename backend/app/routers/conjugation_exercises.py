import json
import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db
from app.models import VerbConjugation, Language
from app.schemas import (
    SentenceGenerateRequest,
    SentenceExerciseItem,
    SentenceCheckRequest,
    SentenceCheckResponse,
)
from app.services.llm import llm_client
from app.services.exercise_gen import LANGUAGE_NAMES
from app.services.conjugation_utils import resolve_compound_form

router = APIRouter(prefix="/conjugation-exercises", tags=["conjugation-exercises"])

# Forms that are genuinely interchangeable (e.g. haber 3s presente: "hay" vs "ha")
_ALTERNATES: dict[str, list[str]] = {
    "hay": ["ha"],
    "ha":  ["hay"],
}


def _forms_match(user: str, correct: str) -> bool:
    u = user.strip().lower()
    c = correct.strip().lower()
    return u == c or u in _ALTERNATES.get(c, [])


PERSON_DESC = {
    "1s": "1st person singular",
    "2s": "2nd person singular",
    "3s": "3rd person singular",
    "1p": "1st person plural",
    "2p": "2nd person plural",
    "3p": "3rd person plural",
}


@router.post("/sentence/generate", response_model=list[SentenceExerciseItem])
async def generate_sentences(req: SentenceGenerateRequest, db: AsyncSession = Depends(get_db)):
    exercises: list[SentenceExerciseItem] = []
    attempts = 0
    max_attempts = req.count * 4

    while len(exercises) < req.count and attempts < max_attempts:
        attempts += 1

        query = select(VerbConjugation).where(
            VerbConjugation.language == req.language,
            VerbConjugation.person.in_(["1s", "2s", "3s", "1p", "2p", "3p"]),
        )
        if req.tenses:
            from sqlalchemy import or_, and_
            tense_conditions = [
                and_(
                    func.lower(VerbConjugation.mood) == t.mood.lower(),
                    func.lower(VerbConjugation.tense) == t.tense.lower(),
                )
                for t in req.tenses
            ]
            query = query.where(or_(*tense_conditions))

        result = await db.execute(query.order_by(func.random()).limit(1))
        row = result.scalar_one_or_none()
        if row is None:
            raise HTTPException(400, "No conjugation data found for the requested tenses")

        lang_name = LANGUAGE_NAMES[req.language]
        person_desc = PERSON_DESC.get(row.person, row.person)
        correct_form = await resolve_compound_form(db, req.language, row.tense, row.person, row.form)

        messages = [
            {
                "role": "system",
                "content": "You are a language teacher. Respond with valid JSON only, no extra text.",
            },
            {
                "role": "user",
                "content": (
                    f"Write a natural {lang_name} sentence that uses the verb '{row.verb_infinitive}' "
                    f"in this exact conjugated form: '{correct_form}' "
                    f"({row.mood} — {row.tense}, {person_desc}). "
                    f"Replace only the conjugated verb form with '___' in the sentence. "
                    f"Return JSON with exactly these keys: "
                    f'"sentence" (the sentence with ___), '
                    f'"subject_hint" (the grammatical subject as it appears in the sentence, e.g. "je", "nous", "María").'
                ),
            },
        ]

        try:
            data = await llm_client.chat_json(messages)
            sentence = data.get("sentence", "").strip()
            subject_hint = data.get("subject_hint", "").strip()
            if not sentence or "___" not in sentence:
                continue
            exercises.append(
                SentenceExerciseItem(
                    sentence=sentence,
                    subject_hint=subject_hint,
                    verb_infinitive=row.verb_infinitive,
                    mood=row.mood,
                    tense=row.tense,
                    person=row.person,
                    correct_form=correct_form,
                )
            )
        except (json.JSONDecodeError, KeyError, httpx.HTTPStatusError, httpx.RequestError):
            continue

    if not exercises:
        raise HTTPException(502, "Could not generate exercises — LLM returned invalid responses")

    return exercises


@router.post("/sentence/check", response_model=SentenceCheckResponse)
async def check_sentence(req: SentenceCheckRequest):
    form_correct = _forms_match(req.user_form, req.item.correct_form)
    tense_correct = (
        req.user_mood.lower() == req.item.mood.lower()
        and req.user_tense.lower() == req.item.tense.lower()
    )

    lang_name = LANGUAGE_NAMES[req.language]
    person_desc = PERSON_DESC.get(req.item.person, req.item.person)

    messages = [
        {
            "role": "system",
            "content": "You are a language teacher giving clear, encouraging feedback.",
        },
        {
            "role": "user",
            "content": (
                f"In {lang_name}: sentence '{req.item.sentence}', "
                f"verb '{req.item.verb_infinitive}', correct form '{req.item.correct_form}' "
                f"({req.item.mood} — {req.item.tense}, {person_desc}). "
                f"Student answered: form='{req.user_form}', "
                f"tense='{req.user_mood} — {req.user_tense}'. "
                f"Form is {'correct' if form_correct else 'INCORRECT'}. "
                f"Tense identification is {'correct' if tense_correct else 'INCORRECT'}. "
                f"In 2-3 sentences: explain why '{req.item.correct_form}' is correct, "
                f"when the {req.item.tense} is used, "
                f"and if the student made errors, explain what was wrong and why."
            ),
        },
    ]

    try:
        explanation = await llm_client.chat(messages)
    except (httpx.HTTPStatusError, httpx.RequestError) as e:
        raise HTTPException(502, "LLM unavailable — ensure Ollama is running")

    return SentenceCheckResponse(
        form_correct=form_correct,
        tense_correct=tense_correct,
        explanation=explanation,
    )
