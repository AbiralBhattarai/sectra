"""Output port for structured LLM completions."""

from typing import Any, Protocol


class LLMPort(Protocol):
    async def complete_json(self, system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]:
        """Ask for a JSON object matching ``schema``. Raises ``LLMException`` when the
        provider fails and ``InvalidLLMOutputException`` when the reply isn't JSON.
        The caller still validates the object against the schema."""
        ...
