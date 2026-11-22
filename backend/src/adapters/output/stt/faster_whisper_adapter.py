import asyncio
import logging
import threading
from concurrent.futures import Executor
from pathlib import Path

from faster_whisper import WhisperModel

from src.adapters.output.stt.wav_span import read_samples
from src.domain.exceptions import TranscriptionException
from src.domain.models.speech import TimeSpan
from src.domain.models.transcript import Segment, Transcript, Word
from src.utils.concurrency import run_blocking

logger = logging.getLogger(__name__)


class FasterWhisperAdapter:
    """Local Whisper via CTranslate2 (CPU int8, or CUDA). The model loads on first use, so the
    worker starts fast and the API never pays for it. CTranslate2 releases the GIL,
    so ``workers`` chunks can genuinely run in parallel on executor threads."""

    def __init__(
        self,
        model_name: str,
        workers: int,
        semaphore: asyncio.Semaphore,
        executor: Executor,
        download_root: Path | None = None,
        device: str = "cpu",
        compute_type: str | None = None,
    ) -> None:
        self._model_name = model_name
        self._workers = workers
        self._semaphore = semaphore
        self._executor = executor
        self._download_root = download_root
        self._device = device
        # int8_float16: int8 weights with fp16 maths, the smallest VRAM footprint on a GPU.
        self._compute_type = compute_type or ("int8" if device == "cpu" else "int8_float16")
        self._model: WhisperModel | None = None
        self._load_lock = threading.Lock()

    async def transcribe(self, wav: Path, span: TimeSpan, language: str | None) -> Transcript:
        async with self._semaphore:
            return await run_blocking(self._executor, self._transcribe, wav, span, language)

    def _transcribe(self, wav: Path, span: TimeSpan, language: str | None) -> Transcript:
        try:
            return self._run(self._load(), wav, span, language)
        except TranscriptionException as exc:
            # CUDA libraries load lazily, so a GPU without them (an image built without
            # docker-compose.gpu.yaml) only fails here: switch to the CPU and retry once.
            if not self._fall_back_to_cpu(exc):
                raise
            return self._run(self._load(), wav, span, language)

    def _fall_back_to_cpu(self, exc: Exception) -> bool:
        message = str(exc).lower()
        if not any(word in message for word in ("cuda", "cublas", "cudnn")):
            return False
        with self._load_lock:
            if self._device != "cpu":
                logger.warning("Whisper on %s failed (%s); using the CPU", self._device, exc)
                self._device, self._compute_type, self._model = "cpu", "int8", None
        return True

    def _run(
        self, model: WhisperModel, wav: Path, span: TimeSpan, language: str | None
    ) -> Transcript:
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
                try:
                    self._model = self._build(self._device, self._compute_type)
                except RuntimeError as exc:
                    if self._device == "cpu":
                        raise
                    # No GPU in the container (started without docker-compose.gpu.yaml) or
                    # a driver mismatch: slower, but the job still finishes.
                    logger.warning("Whisper on %s failed (%s); using the CPU", self._device, exc)
                    self._device, self._compute_type = "cpu", "int8"
                    self._model = self._build("cpu", "int8")
            return self._model

    def _build(self, device: str, compute_type: str) -> WhisperModel:
        return WhisperModel(
            self._model_name,
            device=device,
            compute_type=compute_type,
            num_workers=self._workers,
            download_root=str(self._download_root) if self._download_root else None,
        )
