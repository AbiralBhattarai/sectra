import asyncio
import wave
from collections.abc import Awaitable, Callable
from concurrent.futures import Executor
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort
import python_speech_features

from src.adapters.output.media.ffmpeg_process import stream_frames
from src.domain.models.face_track import FRAME_RATE, FaceTrack
from src.domain.models.speech import TimeSpan
from src.utils.concurrency import run_blocking, threadsafe_progress

_ANALYSIS_LONG_SIDE = 1280  # frames are decoded at most this big
_DETECT_WIDTH = 640  # YuNet runs on a downscale; boxes are scaled back
_MIN_FACE_SCORE = 0.8
_MATCH_IOU = 0.5  # detection joins a track above this overlap
_MAX_GAP = 10  # frames a track survives without a detection
_MIN_FRAMES = 10  # shorter tracks are dropped (Light-ASD demo values)
_BOX_SMOOTHING = 0.5  # weight of a new detection in the running box
_CROP_SCALE = 0.4  # Light-ASD's padding around the face box
_CROP_SIZE = 112
_SAMPLE_RATE = 16_000
_MFCC_PER_FRAME = 4  # 100 MFCC frames/s against 25 video frames/s
_DECODE_SHARE = 0.7  # of the progress bar; scoring takes the rest


class OnnxFaceTrackerAdapter:
    """YuNet faces + Light-ASD speaking scores, both on onnxruntime/OpenCV CPU.

    Frames stream out of ffmpeg one at a time; each tracked face keeps only its 112 px
    grayscale mouth-and-face crop (what Light-ASD consumes), never whole frames. The
    ffmpeg decode lasts the whole job, so it takes this adapter's ``semaphore`` rather
    than the shared ffmpeg one, which would block exports meanwhile. The ONNX session is
    built per job with ``threads`` intra-op threads, so nothing stays loaded between."""

    def __init__(
        self,
        face_model: Path,
        asd_model: Path,
        semaphore: asyncio.Semaphore,
        executor: Executor,
        threads: int,
        durations: list[int],
    ) -> None:
        self._face_model = face_model
        self._asd_model = asd_model
        self._semaphore = semaphore
        self._executor = executor
        self._threads = threads
        self._durations = durations

    async def track(
        self,
        source: Path,
        audio: Path,
        span: TimeSpan,
        source_size: tuple[int, int],
        on_progress: Callable[[float], Awaitable[None]],
    ) -> list[FaceTrack]:
        report = threadsafe_progress(on_progress, asyncio.get_running_loop())
        width, height = _analysis_size(*source_size)
        async with self._semaphore:
            tracker = await run_blocking(self._executor, _Tracker, self._face_model, width, height)
            args = [
                "-ss", f"{span.start:.3f}", "-t", f"{span.duration:.3f}", "-i", str(source),
                "-an", "-vf", f"fps={FRAME_RATE},scale={width}:{height}",
                "-pix_fmt", "bgr24", "-f", "rawvideo", "pipe:1",
            ]  # fmt: skip
            expected = max(1, round(span.duration * FRAME_RATE))
            async for frame in stream_frames(args, width * height * 3):
                await run_blocking(self._executor, tracker.add, frame)
                report(_DECODE_SHARE * min(tracker.frame / expected, 1.0))
            tracks = tracker.finish()
            return await run_blocking(self._executor, self._score, tracks, audio, span, report)

    def _score(
        self,
        tracks: list["_Track"],
        audio: Path,
        span: TimeSpan,
        report: Callable[[float], None],
    ) -> list[FaceTrack]:
        if not tracks:
            return []
        mfcc = python_speech_features.mfcc(
            _read_span(audio, span), _SAMPLE_RATE, numcep=13, winlen=0.025, winstep=0.010
        ).astype(np.float32)
        options = ort.SessionOptions()
        options.intra_op_num_threads = self._threads
        options.inter_op_num_threads = 1
        session = ort.InferenceSession(
            str(self._asd_model), options, providers=["CPUExecutionProvider"]
        )
        scored = []
        for index, track in enumerate(tracks):
            start = track.first_frame * _MFCC_PER_FRAME
            frames = min(len(track.crops), (len(mfcc) - start) // _MFCC_PER_FRAME)
            if frames > 0:
                video = np.stack(track.crops[:frames]).astype(np.float32)
                sound = mfcc[start : start + frames * _MFCC_PER_FRAME]
                # Light-ASD's demo averages passes over chunks of several lengths.
                scores = np.mean(
                    [_run_chunks(session, sound, video, s) for s in self._durations], axis=0
                )
                scored.append(
                    FaceTrack(
                        id=track.id,
                        first_frame=track.first_frame,
                        centres=track.centres[:frames],
                        scores=[round(float(s), 3) for s in scores],
                    )
                )
            report(_DECODE_SHARE + (1 - _DECODE_SHARE) * (index + 1) / len(tracks))
        return scored


@dataclass
class _Track:
    id: int
    first_frame: int
    box: np.ndarray  # smoothed x, y, w, h in analysis pixels
    last_seen: int
    centres: list[tuple[float, float]] = field(default_factory=list)
    crops: list[np.ndarray] = field(default_factory=list)


class _Tracker:
    """Greedy IoU tracker fed one frame at a time (from one thread at a time)."""

    def __init__(self, model: Path, width: int, height: int) -> None:
        self._width, self._height = width, height
        self._scale = min(1.0, _DETECT_WIDTH / width)
        size = (round(width * self._scale), round(height * self._scale))
        self._detect_size = size
        self._detector = cv2.FaceDetectorYN.create(str(model), "", size, _MIN_FACE_SCORE)
        self._active: list[_Track] = []
        self._done: list[_Track] = []
        self._next_id = 0
        self.frame = 0

    def add(self, raw: bytes) -> None:
        image = np.frombuffer(raw, np.uint8).reshape(self._height, self._width, 3)
        small = cv2.resize(image, self._detect_size, interpolation=cv2.INTER_AREA)
        _, faces = self._detector.detect(small)
        boxes = [] if faces is None else [f[:4].astype(np.float64) / self._scale for f in faces]
        self._match(boxes)

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        for track in self._active:
            # A face missed this frame keeps its last box, as long as the gap is short.
            x, y, w, h = track.box
            track.centres.append(
                (
                    min(max((x + w / 2) / self._width, 0.0), 1.0),
                    min(max((y + h / 2) / self._height, 0.0), 1.0),
                )
            )
            track.crops.append(_face_crop(gray, track.box))
        self.frame += 1

    def finish(self) -> list[_Track]:
        for track in self._active:
            self._close(track)
        self._active = []
        return self._done

    def _match(self, boxes: list[np.ndarray]) -> None:
        pairs = sorted(
            (
                (_iou(track.box, box), t, b)
                for t, track in enumerate(self._active)
                for b, box in enumerate(boxes)
            ),
            reverse=True,
        )
        matched_tracks: set[int] = set()
        matched_boxes: set[int] = set()
        for overlap, t, b in pairs:
            if overlap < _MATCH_IOU:
                break
            if t in matched_tracks or b in matched_boxes:
                continue
            track = self._active[t]
            track.box = _BOX_SMOOTHING * boxes[b] + (1 - _BOX_SMOOTHING) * track.box
            track.last_seen = self.frame
            matched_tracks.add(t)
            matched_boxes.add(b)

        still_active = []
        for track in self._active:
            if self.frame - track.last_seen > _MAX_GAP:
                self._close(track)
            else:
                still_active.append(track)
        for b, box in enumerate(boxes):
            if b not in matched_boxes:
                still_active.append(_Track(self._next_id, self.frame, box, self.frame))
                self._next_id += 1
        self._active = still_active

    def _close(self, track: _Track) -> None:
        # Drop the held frames after the face was last actually seen.
        keep = track.last_seen - track.first_frame + 1
        del track.centres[keep:], track.crops[keep:]
        if keep >= _MIN_FRAMES:
            self._done.append(track)


def _face_crop(gray: np.ndarray, box: np.ndarray) -> np.ndarray:
    """Light-ASD's crop: its demo pads the box by ``_CROP_SCALE``, resizes to 224 and keeps
    the centre 112 — i.e. a square of 1.4× the half box size, shifted down towards the
    mouth. Edges replicate rather than pad grey, which the model doesn't notice."""
    x, y, w, h = box
    half = max(w, h) / 2
    side = max(2, round(half * (1 + _CROP_SCALE)))
    centre = (float(x + w / 2), float(y + h / 2 + half * _CROP_SCALE))
    patch = cv2.getRectSubPix(gray, (side, side), centre)
    return cv2.resize(patch, (_CROP_SIZE, _CROP_SIZE), interpolation=cv2.INTER_AREA)


def _iou(a: np.ndarray, b: np.ndarray) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    w = min(ax + aw, bx + bw) - max(ax, bx)
    h = min(ay + ah, by + bh) - max(ay, by)
    if w <= 0 or h <= 0:
        return 0.0
    inter = w * h
    return float(inter / (aw * ah + bw * bh - inter))


def _run_chunks(
    session: ort.InferenceSession, audio: np.ndarray, video: np.ndarray, seconds: int
) -> np.ndarray:
    step = seconds * FRAME_RATE
    parts = [
        session.run(
            None,
            {
                "audio": audio[None, i * _MFCC_PER_FRAME : (i + step) * _MFCC_PER_FRAME],
                "video": video[None, i : i + step],
            },
        )[0]
        for i in range(0, len(video), step)
    ]
    return np.concatenate(parts)


def _read_span(audio: Path, span: TimeSpan) -> np.ndarray:
    with wave.open(str(audio), "rb") as reader:
        reader.setpos(min(round(span.start * _SAMPLE_RATE), reader.getnframes()))
        frames = reader.readframes(round(span.duration * _SAMPLE_RATE))
    return np.frombuffer(frames, dtype=np.int16)


def _analysis_size(width: int, height: int) -> tuple[int, int]:
    scale = min(1.0, _ANALYSIS_LONG_SIDE / max(width, height))
    return max(2, round(width * scale / 2) * 2), max(2, round(height * scale / 2) * 2)
