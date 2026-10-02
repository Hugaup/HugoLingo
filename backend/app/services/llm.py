import json
import logging
from collections.abc import AsyncIterator

import httpx
from app.config import settings

log = logging.getLogger(__name__)

# Model families with a separate "thinking" phase. Thinking makes every answer
# several times slower and our prompts don't need it, so it's switched off.
THINKING_MODEL_PREFIXES = ("qwen3", "deepseek-r1")


class LLMClient:
    """Single point of contact for the local Ollama model.

    Swap this implementation to use Claude API or any other provider
    without touching any other file.
    """

    def __init__(self, model: str | None = None, base_url: str | None = None):
        self.base_url = base_url or settings.ollama_url
        self.url = f"{self.base_url}/api/chat"
        self.model = model or settings.ollama_model
        # Timing/token counts of the last non-streamed call (benchmarking, logs)
        self.last_metrics: dict = {}

    def _payload(
        self, messages: list[dict], *, json_mode: bool, max_tokens: int | None, stream: bool,
        temperature: float | None = None,
    ) -> dict:
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": stream,
            # Keep the model in memory between requests: reloading it costs seconds
            "keep_alive": settings.ollama_keep_alive,
            "options": {"num_predict": max_tokens or settings.ollama_max_tokens},
        }
        if temperature is not None:
            payload["options"]["temperature"] = temperature
        if json_mode:
            payload["format"] = "json"
        if self.model.startswith(THINKING_MODEL_PREFIXES):
            payload["think"] = False
        return payload

    async def chat(
        self, messages: list[dict], json_mode: bool = False, max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str:
        payload = self._payload(messages, json_mode=json_mode, max_tokens=max_tokens, stream=False,
                                temperature=temperature)
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(self.url, json=payload)
            response.raise_for_status()
            data = response.json()
        self.last_metrics = {
            k: data.get(k) for k in ("total_duration", "load_duration", "eval_count", "eval_duration")
        }
        return data["message"]["content"]

    async def chat_json(
        self, messages: list[dict], max_tokens: int | None = None, temperature: float | None = None,
    ) -> dict:
        raw = await self.chat(messages, json_mode=True, max_tokens=max_tokens, temperature=temperature)
        return json.loads(raw)

    async def chat_stream(self, messages: list[dict], max_tokens: int | None = None) -> AsyncIterator[str]:
        """Yield the reply piece by piece as the model writes it."""
        payload = self._payload(messages, json_mode=False, max_tokens=max_tokens, stream=True)
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream("POST", self.url, json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    chunk = json.loads(line)
                    if text := chunk.get("message", {}).get("content"):
                        yield text
                    if chunk.get("done"):
                        break

    async def warm_up(self) -> None:
        """Load the model into memory ahead of the first real request (no-op on failure)."""
        payload = {"model": self.model, "messages": [], "keep_alive": settings.ollama_keep_alive}
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                (await client.post(self.url, json=payload)).raise_for_status()
        except httpx.HTTPError as e:
            log.warning("LLM warm-up failed (is Ollama running?): %s", e)


llm_client = LLMClient()
