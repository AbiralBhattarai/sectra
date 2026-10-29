import asyncio
import threading
import wave
from collections.abc import Awaitable, Callable
from concurrent.futures import Executor
from pathlib import Path

import numpy as np
import onnxruntime as ort

from src.domain.exceptions import MediaProcessingException
from src.ports.output.vad_port import FrameProbabilities
from src.utils.concurrency import run_blocking, threadsafe_progress

_SAMPLE_RATE = 16_000
_WINDOW = 512  # samples per frame the model scores (32 ms at 16 kHz)
_CONTEXT = 64  # trailing samples of the previous frame the model expects prepended
_BLOCK_FRAMES = 1_000  # frames read from disk at a time


class SileroOnnxAdapter:
    """Silero VAD (v5+ ONNX interface) on onnxruntime CPU. Inference is a sequential
    loop over 32 ms frames, so each file runs on one ``executor`` thread; the
    ``semaphore`` bounds how many files are scored at once."""

    def __init__(self, model_path: Path, semaphore: asyncio.Semaphore, executor: Executor) -> None:
        self._model_path = model_path
        self._semaphore = semaphore
        self._executor = executor
        self._session: ort.InferenceSession | None = None
        self._load_lock = threading.Lock()

    async def frame_probabilities(
        self, wav: Path, on_progress: Callable[[float], Awaitable[None]]
    ) -> FrameProbabilities:
        report = threadsafe_progress(on_progress, asyncio.get_running_loop())
        async with self._semaphore:
            probabilities = await run_blocking(self._executor, self._score, wav, report)
        return FrameProbabilities(frame_seconds=_WINDOW / _SAMPLE_RATE, probabilities=probabilities)

    def _score(self, wav: Path, report: Callable[[float], None]) -> list[float]:
        session = self._load()
        # Each call gets its own recurrent state, so concurrent files don't mix.
        state = np.zeros((2, 1, 128), dtype=np.float32)
        context = np.zeros((1, _CONTEXT), dtype=np.float32)
        sample_rate = np.array(_SAMPLE_RATE, dtype=np.int64)
        probabilities: list[float] = []

        with wave.open(str(wav), "rb") as reader:
            if (reader.getframerate(), reader.getnchannels(), reader.getsampwidth()) != (
                _SAMPLE_RATE,
                1,
                2,
            ):
                raise MediaProcessingException("VAD expects 16 kHz mono 16-bit WAV")
            total = max(1, reader.getnframes())
            read = 0
            while frames := reader.readframes(_WINDOW * _BLOCK_FRAMES):
                samples = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768
                read += len(samples)
                samples = np.pad(samples, (0, -len(samples) % _WINDOW))
                for window in samples.reshape(-1, _WINDOW):
                    x = np.concatenate([context, window[None, :]], axis=1)
                    output, state = session.run(
                        None, {"input": x, "state": state, "sr": sample_rate}
                    )
                    context = x[:, -_CONTEXT:]
                    probabilities.append(float(output[0][0]))
                report(read / total)
        return probabilities

    def _load(self) -> ort.InferenceSession:
        with self._load_lock:
            if self._session is None:
                options = ort.SessionOptions()
                # The frame loop is sequential; extra intra-op threads only add overhead.
                options.intra_op_num_threads = 1
                options.inter_op_num_threads = 1
                self._session = ort.InferenceSession(
                    str(self._model_path), options, providers=["CPUExecutionProvider"]
                )
            return self._session
