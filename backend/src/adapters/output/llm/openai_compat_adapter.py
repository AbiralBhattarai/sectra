import asyncio
import json
import re
from typing import Any

from openai import APIError, AsyncOpenAI

from src.domain.exceptions import InvalidLLMOutputException, LLMException

_THINKING = re.compile(r"<think>.*?</think>", re.DOTALL)


class OpenAICompatLLMAdapter:
    """Chat completions on any OpenAI-style server: Ollama (``/v1``), OpenAI, Groq,
    OpenRouter, LM Studio, vLLM. Asks for a JSON schema response; servers that
    ignore it still get the schema through the prompt, and the reply is parsed
    leniently. The SDK retries 429/5xx with backoff, honouring ``Retry-After``."""

    def __init__(self, client: AsyncOpenAI, model: str, semaphore: asyncio.Semaphore) -> None:
        self._client = client
        self._model = model
        self._semaphore = semaphore

    async def complete_json(self, system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]:
        async with self._semaphore:
            try:
                response = await self._client.chat.completions.create(
                    model=self._model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    response_format={
                        "type": "json_schema",
                        "json_schema": {"name": "result", "schema": schema},
                    },
                    temperature=0.3,
                )
            except APIError as exc:
                raise LLMException(f"LLM request failed: {exc}") from exc
        return parse_json_object(response.choices[0].message.content or "")


def parse_json_object(text: str) -> dict[str, Any]:
    """The JSON object in ``text``, tolerating reasoning blocks, code fences and
    chatter around it."""
    text = _THINKING.sub("", text)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end < start:
        raise InvalidLLMOutputException(f"No JSON object in LLM reply: {text[:200]!r}")
    try:
        value = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise InvalidLLMOutputException(f"LLM reply is not valid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise InvalidLLMOutputException("LLM reply is not a JSON object")
    return value
