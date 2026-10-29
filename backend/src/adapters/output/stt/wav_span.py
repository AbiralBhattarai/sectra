"""Reads a time span out of a 16 kHz mono WAV, for the STT adapters."""

import io
import wave
from pathlib import Path

import numpy as np

from src.domain.models.speech import TimeSpan


def read_samples(wav: Path, span: TimeSpan) -> np.ndarray:
    """The span as float32 samples in [-1, 1]."""
    frames = _read_frames(wav, span)[0]
    return np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768


def to_wav_bytes(wav: Path, span: TimeSpan) -> bytes:
    """The span as a standalone WAV file, for upload."""
    frames, params = _read_frames(wav, span)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setparams(params)
        writer.writeframes(frames)
    return buffer.getvalue()


def _read_frames(wav: Path, span: TimeSpan) -> tuple[bytes, wave._wave_params]:
    with wave.open(str(wav), "rb") as reader:
        rate = reader.getframerate()
        start = min(int(span.start * rate), reader.getnframes())
        end = min(int(span.end * rate), reader.getnframes())
        reader.setpos(start)
        return reader.readframes(end - start), reader.getparams()
