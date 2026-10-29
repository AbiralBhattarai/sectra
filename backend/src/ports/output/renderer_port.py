"""Output port for rendering a clip to a video file."""

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Protocol

from src.domain.models.render import RenderPlan


class RendererPort(Protocol):
    async def render(
        self,
        plan: RenderPlan,
        source: Path,
        music: Path | None,
        video_out: Path,
        subtitles_out: Path,
        on_progress: Callable[[float], Awaitable[None]],
    ) -> None:
        """Write the MP4 (captions and overlays burned in, music mixed) and an .srt.
        Raises ``MediaProcessingException`` on failure."""
        ...
