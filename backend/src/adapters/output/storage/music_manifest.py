import json
import logging
from pathlib import Path

from src.domain.models.music_track import MusicTrack

logger = logging.getLogger(__name__)


def load_default_tracks(music_dir: Path) -> list[MusicTrack]:
    """Built-in tracks from ``<music_dir>/manifest.json`` whose files are present
    (they're downloaded separately with ``make music``)."""
    manifest = music_dir / "manifest.json"
    if not manifest.is_file():
        logger.info("No built-in music manifest at %s", manifest)
        return []
    entries = json.loads(manifest.read_text())["tracks"]
    tracks = [
        MusicTrack(
            file=entry["file"],
            name=entry["title"],
            artist=entry.get("artist"),
            mood=entry.get("mood"),
            default=True,
        )
        for entry in entries
        if (music_dir / entry["file"]).is_file()
    ]
    if len(tracks) < len(entries):
        logger.warning(
            "%d of %d built-in tracks are missing; run `make music`",
            len(entries) - len(tracks),
            len(entries),
        )
    return tracks
