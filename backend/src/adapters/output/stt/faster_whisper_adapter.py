import asyncio
import threading
from concurrent.futures import Executor
from pathlib import Path

from faster_whisper import WhisperModel

from src.adapters.output.stt.wav_span import read_samples
from src.domain.exceptions import TranscriptionException
from src.domain.models.speech import TimeSpan
from src.domain.models.transcript import Segment, Transcript, Word
from src.utils.concurrency import run_blocking


class FasterWhisperAdapter:
    """Local Whisper via CTranslate2 (CPU, int8). The model loads on first use, so the
    worker starts fast and the API never pays for it. CTranslate2 releases the GIL,
    so ``workers`` chunks can genuinely run in parallel on executor threads."""

    def __init__(
        self,
        model_name: str,
        workers: int,
        semaphore: asyncio.Semaphore,
        executor: Executor,
        download_root: Path | None = None,
    ) -> None:
        self._model_name = model_name
        self._workers = workers
        self._semaphore = semaphore
        self._executor = executor
        self._download_root = download_root
        self._model: WhisperModel | None = None
        self._load_lock = threading.Lock()

    async def transcribe(self, wav: Path, span: TimeSpan, language: str | None) -> Transcript:
        async with self._semaphore:
            return await run_blocking(self._executor, self._transcribe, wav, span, language)

    def _transcribe(self, wav: Path, span: TimeSpan, language: str | None) -> Transcript:
        model = self._load()
        try:
            segments, info = model.transcribe(
                read_samples(wav, span),
                language=language,
                word_timestamps=True,
                vad_filter=False,  # Silero already picked the speech
                # Chunks are independent; conditioning invites repetition loops.
                condition_on_previous_text=False,
            )
            return Transcript(
                language=info.language,
                segments=[
                    Segment(
                        id=index,
                        start=segment.start,
                        end=segment.end,
                        text=segment.text,
                        words=[
                            Word(text=w.word, start=w.start, end=w.end, probability=w.probability)
                            for w in segment.words or []
                        ],
                    )
                    for index, segment in enumerate(segments)  # a generator: runs here
                ],
            )
        except Exception as exc:
            raise TranscriptionException(f"faster-whisper failed: {exc}") from exc

    def _load(self) -> WhisperModel:
        with self._load_lock:
            if self._model is None:
                self._model = WhisperModel(
                    self._model_name,
                    device="cpu",
                    compute_type="int8",
                    num_workers=self._workers,
                    download_root=str(self._download_root) if self._download_root else None,
                )
            return self._model
