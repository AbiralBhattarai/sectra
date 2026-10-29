"""Running ffmpeg/ffprobe as async subprocesses, shared by the media and render adapters."""

import asyncio
from collections.abc import Awaitable, Callable

from src.domain.exceptions import MediaProcessingException

OnProgress = Callable[[float], Awaitable[None]]
OnLine = Callable[[str], Awaitable[None]]


async def run_ffmpeg(
    args: list[str], duration: float | None = None, on_progress: OnProgress | None = None
) -> None:
    """Run ffmpeg with ``args``, reporting progress against ``duration`` (seconds of
    output). Callers hold whatever semaphore bounds ffmpeg concurrency."""
    code, _, stderr = await run_process(
        "ffmpeg", "-hide_banner", "-nostdin", "-y", "-loglevel", "error",
        "-progress", "pipe:1", "-stats_period", "1", *args,
        on_line=_progress_parser(duration, on_progress),
    )  # fmt: skip
    if code != 0:
        raise MediaProcessingException(f"ffmpeg failed: {stderr_tail(stderr)}")


async def run_process(*cmd: str, on_line: OnLine | None = None) -> tuple[int, bytes, bytes]:
    """Run ``cmd``; feed each stdout line to ``on_line`` if given. Kills the process
    if the calling task is cancelled."""
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    try:
        stderr_task = asyncio.create_task(proc.stderr.read())
        if on_line is None:
            stdout = await proc.stdout.read()
        else:
            stdout = b""
            async for line in proc.stdout:
                await on_line(line.decode(errors="replace").strip())
        stderr = await stderr_task
        return await proc.wait(), stdout, stderr
    except BaseException:
        if proc.returncode is None:
            proc.kill()
            await proc.wait()
        raise


def stderr_tail(stderr: bytes, limit: int = 600) -> str:
    return stderr.decode(errors="replace").strip()[-limit:] or "no error output"


def _progress_parser(duration: float | None, on_progress: OnProgress | None) -> OnLine:
    async def on_line(line: str) -> None:
        key, _, value = line.partition("=")
        if key == "out_time_us" and value.isdigit() and on_progress and duration:
            await on_progress(min(int(value) / 1_000_000 / duration, 1.0))

    return on_line
