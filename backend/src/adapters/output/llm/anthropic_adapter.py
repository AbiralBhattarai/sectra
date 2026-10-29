import asyncio
from typing import Any

from anthropic import APIError, AsyncAnthropic

from src.domain.exceptions import InvalidLLMOutputException, LLMException

_TOOL = "submit_result"


class AnthropicLLMAdapter:
    """Claude via the Messages API. Structured output is forced through a single
    tool whose input schema is the requested schema. The SDK retries 429/5xx."""

    def __init__(
        self,
        client: AsyncAnthropic,
        model: str,
        semaphore: asyncio.Semaphore,
        max_tokens: int = 4096,
    ) -> None:
        self._client = client
        self._model = model
        self._semaphore = semaphore
        self._max_tokens = max_tokens

    async def complete_json(self, system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]:
        async with self._semaphore:
            try:
                response = await self._client.messages.create(
                    model=self._model,
                    max_tokens=self._max_tokens,
                    system=system,
                    messages=[{"role": "user", "content": user}],
                    tools=[
                        {
                            "name": _TOOL,
                            "description": "Submit the result.",
                            "input_schema": schema,
                        }
                    ],
                    tool_choice={"type": "tool", "name": _TOOL},
                )
            except APIError as exc:
                raise LLMException(f"LLM request failed: {exc}") from exc
        block = next((b for b in response.content if b.type == "tool_use"), None)
        if block is None or not isinstance(block.input, dict):
            raise InvalidLLMOutputException("Claude did not call the result tool")
        return block.input
