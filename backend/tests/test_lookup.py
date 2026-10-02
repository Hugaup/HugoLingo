"""Clicking a word while reading: look it up, then keep it in "my words"."""
import httpx
import pytest
from sqlalchemy import select

from app.models import Language, VocabItem, VocabReview, WordLookup
from app.services import llm
from app.services.lookup import clean_word, find_curated, singular_guess


@pytest.fixture
def fake_dictionary(monkeypatch):
    """The LLM as a dictionary; records the words it was asked about."""
    asked = []

    async def chat_json(messages, max_tokens=None):
        asked.append(messages[1]["content"])
        return {"lemma": "Correr", "translation": "to run", "pos": "verb"}

    monkeypatch.setattr(llm.llm_client, "chat_json", chat_json)
    return asked


async def lookup(client, word, context="", language="spanish"):
    return await client.post("/vocab/lookup", json={"language": language, "word": word, "context": context})


# ── Finding the word ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,clean", [
    ("Casa,", "casa"), ("¿Tienes", "tienes"), ("l’eau", "l'eau"), ("rendez-vous!", "rendez-vous"),
    ("123", ""), ("—", ""),
])
def test_clean_word(raw, clean):
    assert clean_word(raw) == clean


@pytest.mark.parametrize("language,word,expected", [
    (Language.spanish, "casa", "casa"),
    (Language.spanish, "casas", "casa"),      # plural
    (Language.spanish, "tengo", "tener"),     # verb form → infinitive, via verb_conjugations
    (Language.spanish, "tuvimos", "tener"),
    (Language.french, "l'eau", "eau"),        # elision
])
async def test_find_curated(db, vocab, spanish_verbs, language, word, expected):
    item = await find_curated(db, language, word)
    assert item is not None and item.text == expected


@pytest.mark.parametrize("language,word,singular", [
    (Language.spanish, "bicicletas", "bicicleta"),
    (Language.spanish, "montañeros", "montañero"),
    (Language.spanish, "ciudades", "ciudad"),
    (Language.spanish, "canciones", "canción"),
    (Language.spanish, "coches", "coche"),
    (Language.spanish, "noches", "noche"),
    (Language.spanish, "flores", "flor"),
    (Language.spanish, "luces", "luz"),
    (Language.spanish, "lunes", "lunes"),       # singular despite the -es
    (Language.spanish, "crisis", "crisis"),     # -is / -us nouns are singular
    (Language.spanish, "virus", "virus"),
    (Language.spanish, "mar", "mar"),
    (Language.french, "pays", "pays"),          # French is left to the LLM
    (Language.french, "maisons", "maisons"),
])
def test_singular_guess(language, word, singular):
    assert singular_guess(language, word) == singular


async def test_llm_plural_lemmas_are_singularised(logged_in, vocab, monkeypatch):
    async def lazy_dictionary(messages, max_tokens=None):
        return {"lemma": "bicicletas", "translation": "bicycles", "pos": "noun"}  # what qwen2.5:7b really returns
    monkeypatch.setattr(llm.llm_client, "chat_json", lazy_dictionary)
    alice, _ = await logged_in()
    assert (await lookup(alice, "bicicletas")).json()["lemma"] == "bicicleta"


async def test_find_curated_misses_unknown_words(db, vocab, spanish_verbs):
    assert await find_curated(db, Language.spanish, "correteaban") is None


# ── Looking up ───────────────────────────────────────────────────────────────

async def test_known_words_come_from_the_vocabulary_without_the_llm(logged_in, vocab, spanish_verbs, fake_dictionary):
    alice, _ = await logged_in()
    data = (await lookup(alice, "Tengo", "Tengo dos hermanos.")).json()
    assert (data["lemma"], data["translation"], data["source"], data["in_my_words"]) == ("tener", "to have", "vocabulary", False)
    assert data["item_id"] is not None
    assert fake_dictionary == []


async def test_unknown_words_ask_the_llm_once_then_use_the_cache(logged_in, vocab, fake_dictionary, db):
    alice, _ = await logged_in()
    first = (await lookup(alice, "corría", "El niño corría por el parque.")).json()
    assert (first["lemma"], first["translation"], first["source"], first["item_id"]) == ("correr", "to run", "ai", None)
    assert "El niño corría por el parque." in fake_dictionary[0]  # the sentence is given as context

    second = (await lookup(alice, "Corría")).json()
    assert second["source"] == "dictionary"
    assert len(fake_dictionary) == 1  # no second LLM call
    assert (await db.execute(select(WordLookup.word))).scalars().all() == ["corría"]


async def test_lookup_reports_a_dead_llm(logged_in, vocab, monkeypatch):
    async def down(messages, max_tokens=None):
        raise httpx.ConnectError("ollama down")
    monkeypatch.setattr(llm.llm_client, "chat_json", down)
    alice, _ = await logged_in()
    assert (await lookup(alice, "corría")).status_code == 502


async def test_lookup_rejects_non_words(logged_in, vocab, fake_dictionary):
    alice, _ = await logged_in()
    assert (await lookup(alice, "1234")).status_code == 502
    assert fake_dictionary == []


# ── My words ─────────────────────────────────────────────────────────────────

async def add(client, lemma, translation, example="", language="spanish"):
    r = await client.post("/vocab/my-words", json={
        "language": language, "lemma": lemma, "translation": translation, "example": example,
    })
    assert r.status_code == 200, r.text
    return r.json()


async def test_adding_a_curated_word_schedules_it_for_review(logged_in, vocab, db):
    alice, user = await logged_in()
    data = await add(alice, "casa", "house")
    casa = await db.get(VocabItem, data["item_id"])
    assert (casa.owner_id, casa.kind, data["added"]) == (None, "word", True)  # the shared item, not a copy

    review = (await db.execute(select(VocabReview))).scalar_one()
    assert (review.user_id, review.box) == (user["id"], 0)
    assert (await alice.get("/vocab/spanish/overview")).json()["due"] == 1
    assert (await lookup(alice, "casa")).json()["in_my_words"] is True
    assert (await add(alice, "casa", "house"))["added"] is False  # already there


async def test_adding_an_unknown_word_creates_a_personal_word(logged_in, vocab, db):
    alice, user = await logged_in()
    data = await add(alice, "correr", "to run", "El niño corre por el parque.")
    item = await db.get(VocabItem, data["item_id"])
    assert (item.owner_id, item.kind, item.topic, item.text) == (user["id"], "personal", "my_words", "correr")

    overview = (await alice.get("/vocab/spanish/overview")).json()
    mine = next(g for g in overview["groups"] if g["kind"] == "personal")
    assert (mine["topic"], mine["total"], mine["due"]) == ("my_words", 1, 1)

    session = (await alice.get("/vocab/spanish/session?kind=personal")).json()
    assert [i["text"] for i in session] == ["correr"]
    assert len(session[0]["options"]) == 3  # wrong options come from the shared words
    assert all(o["kind"] == "word" for o in session[0]["options"])

    check = await alice.post("/vocab/check", json={"item_id": item.id, "exercise": "type_to_target", "answer": "correr"})
    assert check.json()["result"] == "correct"


async def test_personal_words_are_private(logged_in, vocab, db):
    alice, _ = await logged_in("alice")
    bob, _ = await logged_in("bob")
    item_id = (await add(alice, "correr", "to run"))["item_id"]

    assert not any(g["kind"] == "personal" for g in (await bob.get("/vocab/spanish/overview")).json()["groups"])
    assert (await bob.get("/vocab/spanish/session?kind=personal")).json() == []
    assert all(r["id"] != item_id for r in (await bob.get("/vocab/spanish/items")).json())
    r = await bob.post("/vocab/check", json={"item_id": item_id, "exercise": "type_to_target", "answer": "correr"})
    assert r.status_code == 404
    assert (await bob.delete(f"/vocab/my-words/{item_id}")).status_code == 404

    # Both users may save the same word independently
    assert (await add(bob, "correr", "to run"))["item_id"] != item_id


async def test_removing_personal_words(logged_in, vocab, db):
    alice, _ = await logged_in()
    item_id = (await add(alice, "correr", "to run"))["item_id"]
    assert (await alice.delete(f"/vocab/my-words/{item_id}")).status_code == 204
    assert await db.get(VocabItem, item_id) is None

    casa_id = (await add(alice, "casa", "house"))["item_id"]
    assert (await alice.delete(f"/vocab/my-words/{casa_id}")).status_code == 404  # shared words can't be deleted


@pytest.mark.parametrize("method,path", [
    ("POST", "/vocab/lookup"), ("POST", "/vocab/my-words"), ("DELETE", "/vocab/my-words/1"),
])
async def test_requires_login(client, method, path):
    assert (await client.request(method, path, json={})).status_code == 401
