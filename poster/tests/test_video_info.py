import struct
from datetime import datetime

from test_outbox import clip

from poster import outbox
from poster.config import load_settings
from poster.video_info import DEFAULT_LIMITS, mp4_duration, too_long


def box(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I4s", 8 + len(payload), kind) + payload


def mvhd_v0(timescale: int, duration: int) -> bytes:
    return box(b"mvhd", b"\x00\x00\x00\x00" + b"\x00" * 8 + struct.pack(">II", timescale, duration))


def mvhd_v1(timescale: int, duration: int) -> bytes:
    return box(
        b"mvhd", b"\x01\x00\x00\x00" + b"\x00" * 16 + struct.pack(">IQ", timescale, duration)
    )


def test_duration_comes_from_the_moov_header(tmp_path):
    video = tmp_path / "a.mp4"
    video.write_bytes(
        box(b"ftyp", b"isom" * 3) + box(b"moov", box(b"udta", b"x") + mvhd_v0(1000, 184_333))
    )
    assert mp4_duration(video) == 184.333

    late = tmp_path / "b.mp4"  # moov after mdat, 64-bit duration
    late.write_bytes(
        box(b"ftyp", b"isom")
        + box(b"mdat", b"\x00" * 50)
        + box(b"moov", mvhd_v1(90_000, 90_000 * 95))
    )
    assert mp4_duration(late) == 95

    junk = tmp_path / "c.mp4"
    junk.write_bytes(b"not an mp4 at all")
    assert mp4_duration(junk) is None
    assert mp4_duration(tmp_path / "missing.mp4") is None


def test_too_long_names_the_platform_and_limit():
    assert too_long(184.3, "instagram", DEFAULT_LIMITS).startswith("Too long for instagram: 184 s")
    assert too_long(180.2, "instagram", DEFAULT_LIMITS) is None  # rounding slack
    assert too_long(150, "x", DEFAULT_LIMITS) is not None
    assert too_long(184, "youtube", DEFAULT_LIMITS) is not None  # would be a normal video
    assert too_long(600, "tiktok", DEFAULT_LIMITS) is None
    assert too_long(None, "instagram", DEFAULT_LIMITS) is None


def test_limits_can_be_raised_per_platform(tmp_path, monkeypatch):
    monkeypatch.setenv("X_MAX_SECONDS", "600")
    settings = load_settings(tmp_path / "missing.env")
    assert settings.max_seconds["x"] == 600
    assert settings.max_seconds["instagram"] == DEFAULT_LIMITS["instagram"]


def test_a_too_long_clip_gives_up_at_once(tmp_path):
    clip(tmp_path / "v", 1, "2026-11-19T10:00:00", caption="long one")
    [item] = outbox.scan(tmp_path)

    outbox.record_failure(
        item, "instagram", datetime.now().astimezone(), "Too long", 3, give_up=True
    )

    [item] = outbox.scan(tmp_path)
    assert item.failures("instagram") == 3
    assert not outbox.is_open(item, "instagram", max_failures=3)
