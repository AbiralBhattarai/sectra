"""Settings from the environment and ``poster/.env`` (environment wins)."""

import os
from dataclasses import dataclass, field
from pathlib import Path

from poster.video_info import DEFAULT_LIMITS

ROOT = Path(__file__).resolve().parents[2]  # the poster/ directory
PLATFORMS = ("youtube", "tiktok", "instagram", "x", "facebook")
#: Posted to when PLATFORMS isn't set.
DEFAULT_PLATFORMS = ("youtube", "tiktok", "instagram", "x")


@dataclass(frozen=True)
class Settings:
    #: Sectra's outbox: ``<video folder>/<rank> <caption>.mp4`` + ``.json`` sidecars.
    outbox_dir: Path = ROOT.parent / "data" / "outbox"
    platforms: tuple[str, ...] = DEFAULT_PLATFORMS
    #: Most posts per platform per local day, spread over the active hours.
    posts_per_day: int = 10
    #: Local hours [start, end) during which posting happens.
    active_hours: tuple[int, int] = (9, 23)
    #: Each gap between posts is the even spacing ± this share, so it never looks clockwork.
    jitter: float = 0.25
    #: Attempts per clip and platform before it's skipped there.
    max_failures: int = 3
    headless: bool = False
    #: "chrome" uses the installed Google Chrome (logins work like a normal browser);
    #: "chromium" uses Playwright's bundled one (`uv run playwright install chromium`).
    browser_channel: str = "chrome"
    #: Explicit Chrome for `poster login`, if it isn't in a standard place.
    chrome_path: Path | None = None
    profiles_dir: Path = ROOT / "profiles"
    logs_dir: Path = ROOT / "logs"
    state_file: Path = ROOT / "state.json"
    #: YouTube: "public", "unlisted" or "private".
    youtube_visibility: str = "public"
    #: Longest clip per platform, seconds (see video_info.DEFAULT_LIMITS).
    max_seconds: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_LIMITS))
    extra: dict[str, str] = field(default_factory=dict)


def load_settings(env_file: Path = ROOT / ".env") -> Settings:
    values = _read_env_file(env_file) | {k: v for k, v in os.environ.items() if k.isupper()}

    def get(name: str) -> str | None:
        value = values.get(name)
        return value.strip() if value and value.strip() else None

    kwargs: dict = {}
    if outbox := get("OUTBOX_DIR"):
        path = Path(outbox)
        kwargs["outbox_dir"] = path if path.is_absolute() else (ROOT / path).resolve()
    if platforms := get("PLATFORMS"):
        chosen = tuple(p.strip().lower() for p in platforms.split(",") if p.strip())
        unknown = set(chosen) - set(PLATFORMS)
        if unknown:
            raise ValueError(f"Unknown PLATFORMS {sorted(unknown)}; choose from {PLATFORMS}")
        kwargs["platforms"] = chosen
    if per_day := get("POSTS_PER_DAY"):
        kwargs["posts_per_day"] = max(1, int(per_day))
    if hours := get("ACTIVE_HOURS"):
        start, end = (int(h) for h in hours.split("-"))
        if not 0 <= start < end <= 24:
            raise ValueError("ACTIVE_HOURS must look like 9-23 (start < end, within 0-24)")
        kwargs["active_hours"] = (start, end)
    if jitter := get("JITTER"):
        kwargs["jitter"] = min(max(float(jitter), 0.0), 0.9)
    if failures := get("MAX_FAILURES"):
        kwargs["max_failures"] = max(1, int(failures))
    if headless := get("HEADLESS"):
        kwargs["headless"] = headless.lower() in ("1", "true", "yes")
    if channel := get("BROWSER_CHANNEL"):
        kwargs["browser_channel"] = channel
    if chrome := get("CHROME_PATH"):
        kwargs["chrome_path"] = Path(chrome)
    if visibility := get("YOUTUBE_VISIBILITY"):
        if visibility not in ("public", "unlisted", "private"):
            raise ValueError("YOUTUBE_VISIBILITY must be public, unlisted or private")
        kwargs["youtube_visibility"] = visibility
    limits = dict(DEFAULT_LIMITS)
    for platform in PLATFORMS:
        if limit := get(f"{platform.upper()}_MAX_SECONDS"):
            limits[platform] = float(limit)
    kwargs["max_seconds"] = limits
    return Settings(**kwargs)


def _read_env_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values
