import json
import httpx
from app.config import settings


class LLMClient:
    """Single point of contact for the local Ollama model.

    Swap this implementation to use Claude API or any other provider
    without touching any other file.
    """

    def __init__(self):
        self.url = f"{settings.ollama_url}/api/chat"
        self.model = settings.ollama_model

    async def chat(self, messages: list[dict], json_mode: bool = False) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
        }
        if json_mode:
            payload["format"] = "json"

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(self.url, json=payload)
            response.raise_for_status()
            data = response.json()
            return data["message"]["content"]

    async def chat_json(self, messages: list[dict]) -> dict:
        raw = await self.chat(messages, json_mode=True)
        return json.loads(raw)


llm_client = LLMClient()
