import json

import httpx
import pytest

from app.services import llm as llm_module
from app.services.llm import LLMClient


# ── Request payload ──────────────────────────────────────────────────────────

def test_payload_keeps_the_model_loaded_and_caps_length():
    p = LLMClient(model="qwen2.5:7b")._payload([], json_mode=False, max_tokens=None, stream=False)
    assert p["keep_alive"] == "30m"
    assert p["options"]["num_predict"] == 600
    assert "format" not in p and "think" not in p


def test_payload_per_call_cap_and_json_mode():
    p = LLMClient(model="qwen2.5:7b")._payload([], json_mode=True, max_tokens=200, stream=False)
    assert (p["options"]["num_predict"], p["format"]) == (200, "json")


@pytest.mark.parametrize("model,think_off", [
    ("qwen3:4b", True), ("qwen3:8b", True), ("deepseek-r1:7b", True),
    ("qwen2.5:7b", False), ("gemma3:4b", False),
])
def test_thinking_is_disabled_only_for_thinking_models(model, think_off):
    p = LLMClient(model=model)._payload([], json_mode=False, max_tokens=None, stream=False)
    assert (p.get("think") is False) == think_off


# ── Talking to a (fake) Ollama ───────────────────────────────────────────────

@pytest.fixture
def fake_ollama(monkeypatch):
    """Route LLMClient's HTTP calls to a handler: set fake_ollama.handler = fn(request) -> Response."""
    real_client = httpx.AsyncClient

    class Fake:
        handler = None
        requests = []

    def factory(**kwargs):
        def handle(request):
            Fake.requests.append(json.loads(request.content or b"{}"))
            return Fake.handler(request)
        return real_client(transport=httpx.MockTransport(handle), **kwargs)

    monkeypatch.setattr(llm_module.httpx, "AsyncClient", factory)
    return Fake


async def test_chat_returns_content_and_records_speed(fake_ollama):
    fake_ollama.handler = lambda r: httpx.Response(200, json={
        "message": {"content": "Hola"}, "eval_count": 50, "eval_duration": 1_000_000_000,
        "total_duration": 1_200_000_000, "load_duration": 10,
    })
    client = LLMClient(model="qwen2.5:3b")
    assert await client.chat([{"role": "user", "content": "hi"}], max_tokens=50) == "Hola"
    assert client.last_metrics["eval_count"] == 50
    assert fake_ollama.requests[-1]["options"]["num_predict"] == 50


async def test_chat_stream_yields_pieces_in_order(fake_ollama):
    lines = [
        {"message": {"content": "Ho"}, "done": False},
        {"message": {"content": "la"}, "done": False},
        {"message": {"content": ""}, "done": True},
    ]
    fake_ollama.handler = lambda r: httpx.Response(200, content="\n".join(json.dumps(l) for l in lines) + "\n")
    pieces = [p async for p in LLMClient(model="qwen3:4b").chat_stream([{"role": "user", "content": "hi"}])]
    assert pieces == ["Ho", "la"]
    sent = fake_ollama.requests[-1]
    assert (sent["stream"], sent["think"]) == (True, False)


async def test_warm_up_never_raises(fake_ollama):
    def down(request):
        raise httpx.ConnectError("ollama down")
    fake_ollama.handler = down
    await LLMClient().warm_up()  # logs a warning instead of crashing startup


# ── /chat/stream ─────────────────────────────────────────────────────────────

async def test_chat_stream_endpoint_sends_text_as_it_arrives(logged_in, monkeypatch):
    async def stream(messages, **kwargs):
        for piece in ["Hola", ", ", "¿qué tal?"]:
            yield piece
    monkeypatch.setattr(llm_module.llm_client, "chat_stream", stream)

    alice, _ = await logged_in()
    r = await alice.post("/chat/stream", json={"messages": [{"role": "user", "content": "hola"}]})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")
    assert r.text == "Hola, ¿qué tal?"


async def test_chat_stream_reports_a_dead_llm_in_the_text(logged_in, monkeypatch):
    async def stream(messages, **kwargs):
        yield "Hola"
        raise httpx.ConnectError("ollama died")
    monkeypatch.setattr(llm_module.llm_client, "chat_stream", stream)

    alice, _ = await logged_in()
    r = await alice.post("/chat/stream", json={"messages": [{"role": "user", "content": "hola"}]})
    assert r.text.startswith("Hola")
    assert "AI is unavailable" in r.text


async def test_chat_stream_requires_login(client):
    assert (await client.post("/chat/stream", json={"messages": []})).status_code == 401
