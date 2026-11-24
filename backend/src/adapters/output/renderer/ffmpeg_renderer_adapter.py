import asyncio
import functools
from collections.abc import Awaitable, Callable
from concurrent.futures import Executor
from pathlib import Path

from src.adapters.output.media.ffmpeg_process import run_ffmpeg
from src.adapters.output.renderer.ass_builder import build_ass
from src.adapters.output.renderer.character_frames import write_character_video
from src.adapters.output.renderer.ffmpeg_command import build_command
from src.adapters.output.renderer.srt_builder import build_srt
from src.domain.models.render import RenderPlan
from src.utils.concurrency import run_blocking


class FfmpegRendererAdapter:
    """Burns captions/overlays in with libass using the same font files as the preview;
    shares the ffmpeg semaphore with the media adapter. A narrator character is drawn
    into its own transparent video first, then overlaid under the captions."""

    def __init__(
        self,
        semaphore: asyncio.Semaphore,
        executor: Executor,
        fonts_dir: Path,
        characters_dir: Path | None = None,
    ) -> None:
        self._semaphore = semaphore
        self._executor = executor
        self._fonts_dir = fonts_dir
        self._characters_dir = characters_dir or Path("../assets/characters")

    async def render(
        self,
        plan: RenderPlan,
        source: Path,
        music: Path | None,
        video_out: Path,
        subtitles_out: Path,
        on_progress: Callable[[float], Awaitable[None]],
    ) -> None:
        ass = video_out.with_suffix(".ass")
        partial = video_out.with_name(f"{video_out.stem}.partial{video_out.suffix}")
        character = video_out.with_name(f"{video_out.stem}.character.mov")
        await run_blocking(
            self._executor, functools.partial(ass.write_text, build_ass(plan), encoding="utf-8")
        )
        try:
            async with self._semaphore:
                if plan.character is not None:
                    await write_character_video(
                        plan, self._characters_dir, character, self._executor
                    )
                await run_ffmpeg(
                    build_command(
                        plan,
                        source,
                        music,
                        ass,
                        self._fonts_dir,
                        partial,
                        character if plan.character is not None else None,
                    ),
                    plan.duration,
                    on_progress,
                )
            partial.replace(video_out)
            await run_blocking(
                self._executor,
                functools.partial(subtitles_out.write_text, build_srt(plan), encoding="utf-8"),
            )
        finally:
            ass.unlink(missing_ok=True)
            character.unlink(missing_ok=True)
            partial.unlink(missing_ok=True)
