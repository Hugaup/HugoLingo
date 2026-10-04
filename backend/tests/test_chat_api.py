import httpx
import pytest

from app.routers.chat import STREAM_ERROR
from app.services import llm


@pytest.fixture
def fake_llm(monkeypatch):
    """Canned replies; set state["fail"] to act as if Ollama were down."""
    state = {"fail": False}

    async def chat(messages, max_tokens=None, temperature=None):
        if state["fail"]:
            raise httpx.ConnectError("ollama is down")
        return "Hello"

    async def chat_stream(messages, max_tokens=None):
        if state["fail"]:
            raise httpx.ConnectError("ollama is down")
        for piece in ["Hel", "lo"]:
            yield piece

    monkeypatch.setattr(llm.llm_client, "chat", chat)
    monkeypatch.setattr(llm.llm_client, "chat_stream", chat_stream)
    return state


MESSAGES = {"messages": [{"role": "user", "content": "Hola"}]}


async def test_chat(logged_in, fake_llm):
    alice, _ = await logged_in()
    r = await alice.post("/chat", json=MESSAGES)
    assert r.status_code == 200 and r.json() == {"content": "Hello"}


async def test_chat_without_ollama_is_a_clear_502(logged_in, fake_llm):
    alice, _ = await logged_in()
    fake_llm["fail"] = True
    r = await alice.post("/chat", json=MESSAGES)
    assert r.status_code == 502 and "Ollama" in r.json()["detail"]


async def test_chat_stream(logged_in, fake_llm):
    alice, _ = await logged_in()
    assert (await alice.post("/chat/stream", json=MESSAGES)).text == "Hello"
    fake_llm["fail"] = True
    r = await alice.post("/chat/stream", json=MESSAGES)
    assert r.status_code == 200 and r.text == STREAM_ERROR
