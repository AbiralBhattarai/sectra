"""Generates small synthetic videos with ffmpeg for media tests."""

import subprocess
from pathlib import Path


def make_video(
    path: Path,
    width: int,
    height: int,
    seconds: float = 2.0,
    vcodec: str = "libx264",
    audio: bool = True,
) -> Path:
    cmd = ["ffmpeg", "-y", "-loglevel", "error",
           "-f", "lavfi", "-i", f"testsrc2=size={width}x{height}:rate=30:duration={seconds}"]  # fmt: skip
    if audio:
        cmd += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}"]
    cmd += ["-c:v", vcodec, "-pix_fmt", "yuv420p"]
    cmd += ["-c:a", "aac", "-shortest"] if audio else []
    subprocess.run([*cmd, str(path)], check=True)
    return path
