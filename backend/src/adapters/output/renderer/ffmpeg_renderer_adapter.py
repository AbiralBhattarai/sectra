import asyncio
from collections.abc import Awaitable, Callable
from concurrent.futures import Executor
from pathlib import Path

from src.adapters.output.media.ffmpeg_process import run_ffmpeg
from src.adapters.output.renderer.ass_builder import build_ass
from src.adapters.output.renderer.ffmpeg_command import build_command
from src.adapters.output.renderer.srt_builder import build_srt
from src.domain.models.render import RenderPlan
from src.utils.concurrency import run_blocking


class FfmpegRendererAdapter:
    """Burns captions/overlays in with libass using the same font files as the preview;
    shares the ffmpeg semaphore with the media adapter."""

    def __init__(self, semaphore: asyncio.Semaphore, executor: Executor, fonts_dir: Path) -> None:
        self._semaphore = semaphore
        self._executor = executor
        self._fonts_dir = fonts_dir

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
        await run_blocking(self._executor, ass.write_text, build_ass(plan))
        try:
            async with self._semaphore:
                await run_ffmpeg(
                    build_command(plan, source, music, ass, self._fonts_dir, partial),
                    plan.duration,
                    on_progress,
                )
            partial.replace(video_out)
            await run_blocking(self._executor, subtitles_out.write_text, build_srt(plan))
        finally:
            ass.unlink(missing_ok=True)
            partial.unlink(missing_ok=True)
