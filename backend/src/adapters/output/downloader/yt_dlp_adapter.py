import asyncio
from collections.abc import Awaitable, Callable
from concurrent.futures import Executor
from pathlib import Path
from typing import Any

from yt_dlp import YoutubeDL
from yt_dlp.utils import YoutubeDLError

from src.domain.exceptions import DownloadException
from src.ports.output.downloader_port import DownloadResult
from src.utils.concurrency import run_blocking, threadsafe_progress


class YtDlpAdapter:
    """yt-dlp is blocking, so each download runs on ``executor``; ``semaphore`` bounds
    how many run at once."""

    def __init__(
        self, semaphore: asyncio.Semaphore, executor: Executor, cookies_file: Path | None
    ) -> None:
        self._semaphore = semaphore
        self._executor = executor
        self._cookies_file = cookies_file

    async def download(
        self, url: str, dest_dir: Path, on_progress: Callable[[float], Awaitable[None]]
    ) -> DownloadResult:
        report = threadsafe_progress(on_progress, asyncio.get_running_loop())
        async with self._semaphore:
            info = await run_blocking(self._executor, self._download, url, dest_dir, report)
        return DownloadResult(
            path=Path(info["requested_downloads"][0]["filepath"]),
            title=info.get("title"),
            duration=info.get("duration"),
        )

    def _download(
        self, url: str, dest_dir: Path, report: Callable[[float], None]
    ) -> dict[str, Any]:
        def hook(status: dict[str, Any]) -> None:
            total = status.get("total_bytes") or status.get("total_bytes_estimate")
            if status["status"] == "downloading" and total:
                # Video and audio download one after the other; the reporter only
                # passes increases, so the bar tracks the (much larger) video part.
                report(status["downloaded_bytes"] / total)

        options: dict[str, Any] = {
            "format": "bv*+ba/b",
            # "res" is the shorter side, so this caps vertical videos at 1080 wide too.
            # Preferring H.264/AAC usually lets normalization stream-copy.
            "format_sort": ["res:1080", "vcodec:h264", "acodec:aac"],
            "merge_output_format": "mp4",
            # YouTube throttles each connection; parallel fragments cut a 27-minute
            # download of a 5.5 h video to a few minutes.
            "concurrent_fragment_downloads": 8,
            "outtmpl": str(dest_dir / "raw.%(ext)s"),
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "progress_hooks": [hook],
        }
        if self._cookies_file:
            options["cookiefile"] = str(self._cookies_file)
        try:
            with YoutubeDL(options) as ydl:
                return ydl.sanitize_info(ydl.extract_info(url, download=True))
        except YoutubeDLError as exc:
            raise DownloadException(str(exc).removeprefix("ERROR: ")) from exc
