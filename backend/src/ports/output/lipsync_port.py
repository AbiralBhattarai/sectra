"""Output port for lip sync: mouth shapes over a narration."""

from pathlib import Path
from typing import Protocol

from src.domain.models.character import MouthCue


class LipSyncPort(Protocol):
    async def mouth_cues(self, wav: Path, transcript: str) -> list[MouthCue]:
        """Mouth shapes (Rhubarb's A–H, X) over ``wav``, sorted and gap-free; the known
        ``transcript`` improves the recognition. Raises ``MediaProcessingException``."""
        ...
