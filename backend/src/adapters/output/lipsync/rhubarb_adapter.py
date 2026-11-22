import asyncio
import json
import tempfile
from pathlib import Path

from src.adapters.output.media.ffmpeg_process import run_process, stderr_tail
from src.domain.exceptions import MediaProcessingException
from src.domain.models.character import MOUTH_SHAPES, MouthCue


class RhubarbLipSyncAdapter:
    """Rhubarb Lip Sync (MIT) as a subprocess. With the narration's text as the dialog
    file it skips speech recognition guesses and only aligns, which is fast and exact
    for clean TTS audio."""

    def __init__(self, binary: Path, semaphore: asyncio.Semaphore) -> None:
        self._binary = binary
        self._semaphore = semaphore

    async def mouth_cues(self, wav: Path, transcript: str) -> list[MouthCue]:
        if not self._binary.is_file():
            raise MediaProcessingException(f"Rhubarb not found at {self._binary}")
        with tempfile.TemporaryDirectory() as tmp:
            dialog = Path(tmp) / "dialog.txt"
            dialog.write_text(transcript, encoding="utf-8")
            async with self._semaphore:
                code, stdout, stderr = await run_process(
                    str(self._binary), "--quiet", "-f", "json", "--extendedShapes", "GHX",
                    "--dialogFile", str(dialog), str(wav),
                )  # fmt: skip
        if code != 0:
            raise MediaProcessingException(f"Rhubarb failed: {stderr_tail(stderr)}")
        return parse_rhubarb(stdout.decode("utf-8", errors="replace"))


def parse_rhubarb(output: str) -> list[MouthCue]:
    try:
        cues = json.loads(output)["mouthCues"]
    except (ValueError, KeyError) as exc:
        raise MediaProcessingException("Rhubarb returned no mouth cues") from exc
    return [
        MouthCue(start=float(c["start"]), end=float(c["end"]), shape=c["value"])
        for c in cues
        if c.get("value") in MOUTH_SHAPES and float(c["end"]) > float(c["start"])
    ]
