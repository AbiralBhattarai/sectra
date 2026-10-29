import asyncio
import json
import wave
from concurrent.futures import Executor
from pathlib import Path
from typing import Any

import numpy as np

from src.adapters.output.media.ffmpeg_process import run_ffmpeg, run_process, stderr_tail
from src.domain.exceptions import MediaProcessingException
from src.domain.models.media import MediaInfo, NormalizePlan
from src.ports.output.media_port import OnProgress
from src.utils.concurrency import run_blocking


class FfmpegMediaAdapter:
    """Runs ffmpeg/ffprobe as async subprocesses. ``semaphore`` bounds how many ffmpeg
    processes run at once across all jobs; ``executor`` runs the numpy waveform pass."""

    def __init__(self, semaphore: asyncio.Semaphore, executor: Executor) -> None:
        self._semaphore = semaphore
        self._executor = executor

    async def probe(self, path: Path) -> MediaInfo:
        code, stdout, stderr = await run_process(
            "ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams",
            str(path),
        )  # fmt: skip
        if code != 0:
            raise MediaProcessingException(f"ffprobe failed: {stderr_tail(stderr)}")
        return _media_info(json.loads(stdout))

    async def normalize(
        self, src: Path, dst: Path, plan: NormalizePlan, duration: float, on_progress: OnProgress
    ) -> None:
        args = ["-i", str(src), "-map", "0:v:0", "-map", "0:a:0"]
        if plan.reencode_video:
            args += _H264 + ["-crf", "20"]
            if plan.scale_to:
                args += ["-vf", "scale={}:{}".format(*plan.scale_to)]
        else:
            args += ["-c:v", "copy"]
        args += ["-c:a", "aac", "-b:a", "192k"] if plan.reencode_audio else ["-c:a", "copy"]
        await self._ffmpeg(args + ["-movflags", "+faststart", str(dst)], duration, on_progress)

    async def extract_audio(self, src: Path, dst: Path) -> None:
        await self._ffmpeg(
            ["-i", str(src), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(dst)]
        )

    async def make_thumbnail(self, src: Path, dst: Path, at_seconds: float) -> None:
        await self._ffmpeg(
            ["-ss", f"{at_seconds:.3f}", "-i", str(src), "-frames:v", "1", "-vf", "scale=-2:360",
             "-q:v", "3", str(dst)]
        )  # fmt: skip

    async def compute_peaks(self, wav: Path, dst: Path, per_second: int) -> None:
        await run_blocking(self._executor, _write_peaks, wav, dst, per_second)

    async def _ffmpeg(
        self, args: list[str], duration: float | None = None, on_progress: OnProgress | None = None
    ) -> None:
        async with self._semaphore:
            await run_ffmpeg(args, duration, on_progress)


_H264 = ["-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p"]


def _media_info(probe: dict[str, Any]) -> MediaInfo:
    streams = probe.get("streams", [])
    video = next(
        (
            s
            for s in streams
            if s.get("codec_type") == "video" and not s.get("disposition", {}).get("attached_pic")
        ),
        None,
    )
    if video is None:
        raise MediaProcessingException("File has no video stream")
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)

    width, height = int(video["width"]), int(video["height"])
    if abs(_rotation(video)) % 180 == 90:
        width, height = height, width
    duration = probe.get("format", {}).get("duration") or video.get("duration")
    if duration is None:
        raise MediaProcessingException("Could not determine the video's duration")
    return MediaInfo(
        duration=float(duration),
        width=width,
        height=height,
        video_codec=video.get("codec_name", "unknown"),
        pixel_format=video.get("pix_fmt"),
        audio_codec=audio.get("codec_name") if audio else None,
    )


def _rotation(stream: dict[str, Any]) -> int:
    for side_data in stream.get("side_data_list", []):
        if "rotation" in side_data:
            return int(float(side_data["rotation"]))
    return int(stream.get("tags", {}).get("rotate", 0))


def _write_peaks(wav: Path, dst: Path, per_second: int) -> None:
    """Max absolute amplitude per 1/per_second slice, scaled to 0..1. Reads the WAV in
    blocks so a multi-hour file never sits in memory whole."""
    peaks: list[np.ndarray] = []
    with wave.open(str(wav), "rb") as reader:
        if reader.getsampwidth() != 2 or reader.getnchannels() != 1:
            raise MediaProcessingException("Expected 16-bit mono WAV for peaks")
        bucket = max(1, reader.getframerate() // per_second)
        while frames := reader.readframes(bucket * 4096):
            samples = np.abs(np.frombuffer(frames, dtype=np.int16).astype(np.int32))
            padded = np.pad(samples, (0, -len(samples) % bucket))
            peaks.append(padded.reshape(-1, bucket).max(axis=1))
    values = np.concatenate(peaks) / 32768 if peaks else np.array([])
    dst.write_text(json.dumps({"per_second": per_second, "peaks": np.round(values, 3).tolist()}))
