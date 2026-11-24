"""The outbox as Sectra writes it: one folder per video holding ``<rank> <caption>.mp4``
and a ``.json`` sidecar. The sidecar (written last) holds the exact caption and is where
the poster records what it posted, so the folder is the whole state of the queue."""

import contextlib
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class Item:
    video: Path
    sidecar: Path
    data: dict[str, Any]

    @property
    def caption(self) -> str:
        # "Post" clicks in Sectra post the clip's title as the description.
        return (
            self.data.get("description")
            or self.data.get("caption")
            or self.data.get("title")
            or self.video.stem
        )

    @property
    def post_now(self) -> bool:
        """Asked for from Sectra's Post button: posted right away by `poster serve`,
        never by the scheduled `poster run`."""
        return bool(self.data.get("post_now"))

    def wanted_on(self, platform: str) -> bool:
        """A Post click names its platforms; scheduled clips go everywhere enabled."""
        wanted = self.data.get("platforms")
        return not wanted or platform in wanted

    @property
    def rank(self) -> int:
        return int(self.data.get("rank") or 999)

    def posted_on(self, platform: str) -> bool:
        return platform in self.data.get("posted", {})

    def failures(self, platform: str) -> int:
        return int(self.data.get("failures", {}).get(platform, {}).get("count", 0))

    def posted_at(self, platform: str) -> datetime | None:
        entry = self.data.get("posted", {}).get(platform)
        return datetime.fromisoformat(entry["at"]) if entry else None


def scan(outbox: Path) -> list[Item]:
    """Every clip with its sidecar, oldest video first, then by rank (best first)."""
    if not outbox.is_dir():
        return []
    items = []
    for sidecar in outbox.glob("*/*.json"):
        video = sidecar.with_suffix(".mp4")
        if not video.is_file():
            continue
        try:
            data = _read(sidecar)
        except (OSError, json.JSONDecodeError):
            continue  # being written, or damaged: skip this round
        items.append(Item(video=video, sidecar=sidecar, data=data))
    first_seen: dict[Path, str] = {}
    for item in items:
        created = str(item.data.get("created_at", ""))
        folder = item.video.parent
        first_seen[folder] = min(first_seen.get(folder, created), created)
    return sorted(items, key=lambda i: (first_seen[i.video.parent], i.video.parent.name, i.rank))


def is_open(item: Item, platform: str, max_failures: int) -> bool:
    """Still to be posted on ``platform``."""
    return (
        item.wanted_on(platform)
        and not item.posted_on(platform)
        and item.failures(platform) < max_failures
    )


def next_for(platform: str, items: list[Item], max_failures: int) -> Item | None:
    """The next scheduled clip (Post-button clips are `poster serve`'s)."""
    return next((i for i in items if not i.post_now and is_open(i, platform, max_failures)), None)


def pending(platform: str, items: list[Item], max_failures: int) -> int:
    return sum(1 for i in items if not i.post_now and is_open(i, platform, max_failures))


def requested(
    items: list[Item], max_failures: int, platforms: tuple[str, ...]
) -> list[tuple[Item, str]]:
    """(clip, platform) pairs asked for with Sectra's Post button and not done yet."""
    return [
        (item, platform)
        for item in items
        if item.post_now
        for platform in platforms
        if is_open(item, platform, max_failures)
    ]


def posted_times(platform: str, items: list[Item]) -> list[datetime]:
    return sorted(t for i in items if (t := i.posted_at(platform)) is not None)


def record_post(item: Item, platform: str, at: datetime, url: str | None) -> None:
    def change(data: dict[str, Any]) -> None:
        data.setdefault("posted", {})[platform] = {"at": at.isoformat(), "url": url}
        data.get("blocked", {}).pop(platform, None)

    _update(item, change)


def record_failure(
    item: Item,
    platform: str,
    at: datetime,
    error: str,
    max_failures: int = 3,
    give_up: bool = False,
) -> None:
    """Count a failed attempt; ``give_up`` when retrying can't help (clip too long)."""

    def change(data: dict[str, Any]) -> None:
        entry = data.setdefault("failures", {}).setdefault(platform, {"count": 0})
        count = int(entry.get("count", 0)) + 1
        if give_up:
            count = max(count, max_failures)
        entry.update(
            count=count, last=at.isoformat(), error=error[:500], gave_up=count >= max_failures
        )

    _update(item, change)


def record_blocked(item: Item, platform: str, at: datetime, reason: str | None) -> None:
    """Note (or clear, with None) why the platform can't post right now (logged out,
    captcha) — not the clip's fault, so it isn't a failure; Sectra shows the reason."""

    def change(data: dict[str, Any]) -> None:
        blocked = data.setdefault("blocked", {})
        if reason is None:
            blocked.pop(platform, None)
        else:
            blocked[platform] = {"at": at.isoformat(), "reason": reason[:300]}

    _update(item, change)


def _partial(sidecar: Path) -> Path:
    return sidecar.with_name(sidecar.name + ".partial")


def _update(item: Item, change) -> None:
    """Re-read, change, write atomically, so a crash never leaves a broken sidecar."""
    data = _read(item.sidecar)
    change(data)
    item.data = data  # what we posted is known even if the file can't be swapped in
    partial = _partial(item.sidecar)
    partial.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    _replace(partial, item.sidecar)


def _read(sidecar: Path) -> dict[str, Any]:
    """The sidecar, or the newer ``.partial`` left by an interrupted update. A partial is
    only ever a complete, newer copy (written in full before the swap), so if it parses
    it wins: otherwise a post recorded there would be forgotten and posted again."""
    partial = _partial(sidecar)
    if partial.is_file():
        try:
            data = json.loads(partial.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass  # cut short while being written: the sidecar is still the truth
        else:
            with contextlib.suppress(OSError):  # still locked: the next update swaps it in
                _replace(partial, sidecar, attempts=1)
            return data
    return json.loads(sidecar.read_text(encoding="utf-8"))


def _replace(partial: Path, sidecar: Path, attempts: int = 12) -> None:
    """``os.replace`` that waits out Windows sharing locks: while another process (Sectra's
    API reading the sidecar through the Docker mount, an antivirus scan) has the file open,
    replacing it fails with "Access is denied" for a moment."""
    delay = 0.05
    for attempt in range(attempts):
        try:
            os.replace(partial, sidecar)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(delay)
            delay = min(delay * 2, 1.0)
