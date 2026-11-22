"""The talking narrator as a transparent video: each layer (SVG) is rasterised once at
the box size, layers are stacked per frame from ``character_timeline``, and the frames
are piped into ffmpeg as a QuickTime RLE (alpha) file that the main render overlays."""

import math
from collections.abc import AsyncIterator, Callable
from concurrent.futures import Executor
from pathlib import Path

import cv2
import numpy as np

from src.adapters.output.media.ffmpeg_process import run_ffmpeg_fed
from src.domain.enums.emotion_enum import Emotion
from src.domain.exceptions import MediaProcessingException
from src.domain.models.render import CharacterPlan, RenderPlan
from src.domain.services.character_timeline import (
    BOB_AMPLITUDE,
    REST,
    blink_starts,
    character_state,
)
from src.domain.services.edl_timing import output_to_source
from src.utils.concurrency import run_blocking

FPS = 30
_BATCH = 30
#: Mouth shape to use when a character lacks one (Rhubarb's own fallbacks).
_MOUTH_FALLBACK = {"G": "B", "H": "C", "X": "A"}


def bob_margin(height: int) -> int:
    """Transparent rows above and below the box, so the idle bob never clips."""
    return math.ceil(BOB_AMPLITUDE * height) + 2


class CharacterLayers:
    """Rasterised, composited layers of one character at one box size (BGRA)."""

    def __init__(self, directory: Path, width: int, height: int) -> None:
        self._directory = directory
        self._width = width
        self._height = height
        self._layers: dict[str, np.ndarray | None] = {}
        self._composites: dict[tuple[str, str, bool], np.ndarray] = {}

    def composite(self, expression: Emotion, mouth: str, blink: bool) -> np.ndarray:
        key = (expression.value, mouth, blink)
        if key not in self._composites:
            base = self._layer(f"base/{expression.value}.svg")
            if base is None:
                base = self._layer("base/neutral.svg")
            if base is None:
                raise MediaProcessingException(f"Character {self._directory.name} has no base")
            image = base.astype(np.float32)
            for overlay in (self._mouth(mouth), self._layer("blink.svg") if blink else None):
                if overlay is not None:
                    image = _over(image, overlay.astype(np.float32))
            self._composites[key] = image.round().astype(np.uint8)
        return self._composites[key]

    def _mouth(self, shape: str) -> np.ndarray | None:
        layer = self._layer(f"mouth/{shape}.svg")
        if layer is None and shape in _MOUTH_FALLBACK:
            layer = self._layer(f"mouth/{_MOUTH_FALLBACK[shape]}.svg")
        return layer

    def _layer(self, name: str) -> np.ndarray | None:
        if name not in self._layers:
            self._layers[name] = _rasterise(self._directory / name, self._width, self._height)
        return self._layers[name]


def _rasterise(svg: Path, width: int, height: int) -> np.ndarray | None:
    """BGRA pixels of ``svg`` at the box size, or None if the layer doesn't exist."""
    if not svg.is_file():
        return None
    import resvg_py

    png = resvg_py.svg_to_bytes(svg_path=str(svg), width=width, height=height)
    image = cv2.imdecode(np.frombuffer(bytes(png), np.uint8), cv2.IMREAD_UNCHANGED)
    if image is None or image.ndim != 3 or image.shape[2] != 4:
        raise MediaProcessingException(f"Could not rasterise {svg}")
    if image.shape[:2] != (height, width):
        image = cv2.resize(image, (width, height), interpolation=cv2.INTER_AREA)
    return image


def _over(below: np.ndarray, above: np.ndarray) -> np.ndarray:
    """Straight-alpha "over" (BGRA float32 0..255)."""
    a_top = above[..., 3:4] / 255
    a_bottom = below[..., 3:4] / 255
    alpha = a_top + a_bottom * (1 - a_top)
    colour = above[..., :3] * a_top + below[..., :3] * a_bottom * (1 - a_top)
    safe = np.where(alpha > 0, alpha, 1)
    return np.concatenate([colour / safe, alpha * 255], axis=-1)


def frame_source(plan: RenderPlan, layers: CharacterLayers) -> tuple[int, Callable[[int], bytes]]:
    """(frame count, frame i → raw BGRA bytes of the padded box)."""
    character: CharacterPlan = plan.character  # type: ignore[assignment]
    margin = bob_margin(character.height)
    canvas = np.zeros((character.height + 2 * margin, character.width, 4), np.uint8)
    blinks = blink_starts(plan.ranges[-1].end + 1)
    count = max(1, math.ceil(plan.duration * FPS))

    def frame(index: int) -> bytes:
        t = output_to_source(index / FPS, plan.ranges)
        state = character_state(character.cues, character.moods, blinks, t)
        offset = margin + round(state.bob * character.height)
        canvas.fill(0)
        canvas[offset : offset + character.height] = layers.composite(
            state.expression, state.mouth or REST, state.blink
        )
        return canvas.tobytes()

    return count, frame


async def write_character_video(
    plan: RenderPlan, characters_dir: Path, dst: Path, executor: Executor
) -> None:
    """Render ``plan.character`` over the clip's whole duration into ``dst`` (.mov)."""
    character = plan.character
    if character is None:
        raise ValueError("The plan has no character")
    directory = characters_dir / character.name
    if not directory.is_dir():
        raise MediaProcessingException(f"Character {character.name!r} is not installed")
    layers = CharacterLayers(directory, character.width, character.height)
    count, frame = frame_source(plan, layers)
    height = character.height + 2 * bob_margin(character.height)

    async def frames() -> AsyncIterator[bytes]:
        for start in range(0, count, _BATCH):
            indices = range(start, min(start + _BATCH, count))
            yield await run_blocking(executor, lambda ix=indices: b"".join(frame(i) for i in ix))

    await run_ffmpeg_fed(
        [
            "-f",
            "rawvideo",
            "-pix_fmt",
            "bgra",
            "-s",
            f"{character.width}x{height}",
            "-r",
            str(FPS),
            "-i",
            "pipe:0",
            "-c:v",
            "qtrle",
            "-pix_fmt",
            "argb",
            str(dst),
        ],  # fmt: skip
        frames(),
    )
