from sqlalchemy import select

from app.models import Exercise, ExerciseType, Language, Progress


async def _grammar_exercise(db) -> Exercise:
    exercise = Exercise(
        type=ExerciseType.grammar,
        language=Language.french,
        difficulty=2,
        content={
            "incorrect_sentence": "Je suis allé au magasin hier et j'ai acheté des pomme.",
            "corrected_sentence": "Je suis allé au magasin hier et j'ai acheté des pommes.",
            "explanation": "Plural noun needs an -s.",
        },
    )
    db.add(exercise)
    await db.commit()
    return exercise


async def test_answers_are_recorded_for_the_logged_in_user(logged_in, db):
    alice, alice_user = await logged_in("alice")
    bob, _ = await logged_in("bob")
    exercise = await _grammar_exercise(db)

    r = await alice.post("/exercises/check", json={
        "exercise_id": exercise.id,
        "user_answer": "Je suis allé au magasin hier et j'ai acheté des pommes.",
    })
    assert r.status_code == 200
    assert r.json()["is_correct"] is True

    alice_stats = (await alice.get("/progress")).json()
    assert (alice_stats["total"], alice_stats["correct"]) == (1, 1)
    assert alice_stats["by_type"]["grammar"]["total"] == 1

    bob_stats = (await bob.get("/progress")).json()
    assert bob_stats["total"] == 0

    row = (await db.execute(select(Progress))).scalar_one()
    assert row.user_id == alice_user["id"]


async def test_client_cannot_record_answers_as_someone_else(logged_in, db):
    alice, alice_user = await logged_in("alice")
    _, bob_user = await logged_in("bob")
    exercise = await _grammar_exercise(db)

    # The old API accepted user_id in the body; it must now be ignored
    await alice.post("/exercises/check", json={
        "exercise_id": exercise.id, "user_answer": "wrong", "user_id": bob_user["id"],
    })
    row = (await db.execute(select(Progress))).scalar_one()
    assert row.user_id == alice_user["id"]
    assert row.is_correct is False
