"""Output port for rendering a clip to a video file."""

from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path
from typing import Protocol

from src.domain.models.render import RenderPlan


class RendererPort(Protocol):
    async def render(
        self,
        plan: RenderPlan,
        inputs: Mapping[str, Path],
        music: Path | None,
        video_out: Path,
        subtitles_out: Path,
        on_progress: Callable[[float], Awaitable[None]],
    ) -> None:
        """Write the MP4 (captions and overlays burned in, music mixed) and an .srt.
        ``inputs`` maps every ``input`` key of the plan's segments and B-roll to a file.
        Raises ``MediaProcessingException`` on failure."""
        ...
