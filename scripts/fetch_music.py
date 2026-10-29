#!/usr/bin/env python3
"""Download Sectra's default background-music library (all CC0) listed in
assets/music/manifest.json into assets/music/. Safe to re-run: existing files are
skipped. Standard library only."""

from __future__ import annotations

import json
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

MUSIC_DIR = Path(__file__).resolve().parent.parent / "assets" / "music"
MIN_BYTES = 100_000  # anything smaller is an error page, not a track


def fetch(track: dict) -> str | None:
    target = MUSIC_DIR / track["file"]
    if target.is_file() and target.stat().st_size >= MIN_BYTES:
        return None
    partial = target.with_suffix(".part")
    try:
        request = urllib.request.Request(track["url"], headers={"User-Agent": "sectra-music-fetch"})
        with urllib.request.urlopen(request, timeout=120) as response, open(partial, "wb") as out:
            while chunk := response.read(1 << 16):
                out.write(chunk)
        if partial.stat().st_size < MIN_BYTES:
            raise ValueError("download too small")
        partial.replace(target)
        return None
    except Exception as exc:  # noqa: BLE001 - report every failure, keep going
        partial.unlink(missing_ok=True)
        return f"{track['title']} ({track['url']}): {exc}"


def main() -> int:
    tracks = json.loads((MUSIC_DIR / "manifest.json").read_text())["tracks"]
    print(f"Fetching {len(tracks)} CC0 tracks into {MUSIC_DIR} …")
    with ThreadPoolExecutor(4) as pool:
        failures = [error for error in pool.map(fetch, tracks) if error]
    present = sum((MUSIC_DIR / t["file"]).is_file() for t in tracks)
    print(f"{present}/{len(tracks)} tracks present.")
    for failure in failures:
        print("  failed:", failure, file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
