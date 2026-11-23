"""A clip's length read from its MP4 header (stdlib only, no ffprobe), and how long each
platform accepts."""

import struct
from pathlib import Path

#: Longest video each platform takes through its web uploader, in seconds. Instagram
#: reels stop at 3 minutes; X allows 2:20 without Premium (raise it with X_MAX_SECONDS).
#: YouTube (anything over 3 min just isn't a Short) and TikTok (10 min) aren't limited.
DEFAULT_LIMITS: dict[str, float] = {"instagram": 180, "x": 140}

_CONTAINERS = {b"moov"}


def mp4_duration(path: Path) -> float | None:
    """Seconds, from the ``moov/mvhd`` box; None if the file can't be read as an MP4."""
    try:
        with path.open("rb") as file:
            return _find_mvhd(file, path.stat().st_size)
    except (OSError, struct.error, ValueError):
        return None


def _find_mvhd(file, end: int) -> float | None:
    while file.tell() + 8 <= end:
        start = file.tell()
        size, kind = struct.unpack(">I4s", file.read(8))
        header = 8
        if size == 1:
            size = struct.unpack(">Q", file.read(8))[0]
            header = 16
        elif size == 0:
            size = end - start
        if size < header:
            return None
        if kind in _CONTAINERS:
            found = _find_mvhd(file, start + size)
            if found is not None:
                return found
        elif kind == b"mvhd":
            version = file.read(1)[0]
            file.read(3)  # flags
            if version == 1:
                file.read(16)
                timescale, duration = struct.unpack(">IQ", file.read(12))
            else:
                file.read(8)
                timescale, duration = struct.unpack(">II", file.read(8))
            return duration / timescale if timescale else None
        file.seek(start + size)
    return None


def too_long(seconds: float | None, platform: str, limits: dict[str, float]) -> str | None:
    """Why the clip can't go to ``platform``, or None when it fits (or its length is unknown)."""
    limit = limits.get(platform)
    if seconds is None or limit is None or seconds <= limit + 0.5:
        return None
    return (
        f"Too long for {platform}: {seconds:.0f} s, the limit is {limit:.0f} s. "
        "Trim the clip in Sectra and post it again."
    )
