"""Input port: Narrator stories."""

from pathlib import Path
from typing import Protocol

from src.domain.models.story import StorySpec
from src.domain.models.video import Video


class StoryPort(Protocol):
    async def create(self, spec: StorySpec) -> Video:
        """Register the story and queue its narration. Raises ``AppValidationException``
        for unknown voices, characters or backgrounds."""
        ...

    def options(self) -> dict:
        """Voices and characters the story form offers."""
        ...

    async def character_layer(self, name: str, layer: str) -> Path:
        """A character's SVG layer (``base/<expr>.svg``, ``mouth/<shape>.svg``,
        ``blink.svg``); raises ``NotFoundException``."""
        ...
