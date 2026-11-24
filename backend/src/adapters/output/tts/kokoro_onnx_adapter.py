import asyncio
import logging
import threading
import wave
from collections.abc import Awaitable, Callable
from concurrent.futures import Executor
from pathlib import Path

import numpy as np

from src.domain.exceptions import SpeechSynthesisException
from src.utils.concurrency import run_blocking

# phonemizer warns "words count mismatch" on most sentences; it's harmless for Kokoro.
logging.getLogger("phonemizer").setLevel(logging.ERROR)

#: Kokoro's accent comes from the voice prefix: a = American, b = British English.
_LANGUAGES = {"a": "en-us", "b": "en-gb"}


class KokoroOnnxAdapter:
    """Kokoro-82M through kokoro-onnx, on the CPU. The model loads on first use (about a
    second); each sentence is synthesised on ``executor`` under ``semaphore``."""

    def __init__(
        self,
        model_path: Path,
        voices_path: Path,
        semaphore: asyncio.Semaphore,
        executor: Executor,
    ) -> None:
        self._model_path = model_path
        self._voices_path = voices_path
        self._semaphore = semaphore
        self._executor = executor
        self._kokoro = None
        self._load_lock = threading.Lock()

    async def narrate(
        self,
        sentences: list[str],
        voice: str,
        speed: float,
        pause_seconds: float,
        dst: Path,
        on_progress: Callable[[float], Awaitable[None]],
    ) -> float:
        if not sentences:
            raise SpeechSynthesisException("Nothing to narrate")
        lang = _LANGUAGES.get(voice[:1], "en-us")
        rate = 24_000
        samples = 0
        partial = dst.with_name(f"{dst.name}.partial")
        writer = await run_blocking(self._executor, _open_wav, partial, rate)
        try:
            async with self._semaphore:
                for index, sentence in enumerate(sentences):
                    audio, rate = await run_blocking(
                        self._executor, self._speak, sentence, voice, speed, lang
                    )
                    if index:
                        silence = np.zeros(round(pause_seconds * rate), dtype=np.int16)
                        await run_blocking(self._executor, writer.writeframes, silence.tobytes())
                        samples += len(silence)
                    pcm = (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16)
                    await run_blocking(self._executor, writer.writeframes, pcm.tobytes())
                    samples += len(pcm)
                    await on_progress((index + 1) / len(sentences))
        except BaseException:
            await run_blocking(self._executor, writer.close)
            partial.unlink(missing_ok=True)
            raise
        await run_blocking(self._executor, writer.close)
        partial.replace(dst)
        return samples / rate

    def _speak(self, text: str, voice: str, speed: float, lang: str) -> tuple[np.ndarray, int]:
        try:
            audio, rate = self._model().create(text, voice=voice, speed=speed, lang=lang)
        except Exception as exc:  # the library raises plain errors (bad voice, phonemizer)
            raise SpeechSynthesisException(f"Kokoro failed on {text[:60]!r}: {exc}") from exc
        return np.asarray(audio, dtype=np.float32), rate

    def _model(self):
        with self._load_lock:
            if self._kokoro is None:
                from kokoro_onnx import Kokoro

                if not self._model_path.is_file() or not self._voices_path.is_file():
                    raise SpeechSynthesisException(
                        f"Kokoro model files missing ({self._model_path}, {self._voices_path});"
                        " run `make models`"
                    )
                self._kokoro = Kokoro(str(self._model_path), str(self._voices_path))
            return self._kokoro


def _open_wav(path: Path, rate: int) -> wave.Wave_write:
    writer = wave.open(str(path), "wb")  # noqa: SIM115 - closed by narrate() after streaming
    writer.setnchannels(1)
    writer.setsampwidth(2)
    writer.setframerate(rate)
    return writer
