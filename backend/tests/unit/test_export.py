"""Export: the API side (queueing, downloads) and a real ffmpeg render."""

import asyncio
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from src.adapters.output.persistence.postgres_clip_repository import PostgresClipRepository
from src.adapters.output.persistence.postgres_video_repository import PostgresVideoRepository
from src.adapters.output.renderer.ffmpeg_renderer_adapter import FfmpegRendererAdapter
from src.api_main import create_app
from src.config.settings import Settings
from src.domain.enums.caption_style_enum import CaptionStyle
from src.domain.models.edl import Captions, Edl, Music, Overlay
from src.domain.models.speech import TimeSpan
from src.domain.models.transcript import Word
from src.domain.models.video import Video
from src.domain.services.render_planning import plan_render
from tests.conftest import TEST_DATABASE_URL, TEST_REDIS_URL
from tests.unit.media_samples import make_video
from tests.unit.test_postgres_clip_repository import make_clip

FONTS = Path(__file__).parents[3] / "assets" / "fonts"


@pytest.fixture
async def client(pg_sessionmaker, redis, tmp_path):
    settings = Settings(database_url=TEST_DATABASE_URL, redis_url=TEST_REDIS_URL, data_dir=tmp_path)
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


async def test_export_is_queued_on_the_render_stream_with_an_edl_snapshot(
    client, pg_sessionmaker, redis
):
    video = Video(title="talk", duration=120, width=1920, height=1080)
    await PostgresVideoRepository(pg_sessionmaker).add(video)
    clip = make_clip(video, 30, 80)
    await PostgresClipRepository(pg_sessionmaker).replace_for_video(video.id, [clip])

    response = await client.post(f"/api/clips/{clip.id}/exports")

    assert response.status_code == 202
    export = response.json()
    assert (export["status"], export["video_url"]) == ("queued", None)
    entries = await redis.xrange("jobs:render")
    assert [fields["job_id"] for _, fields in entries] == [export["id"]]
    assert await redis.xlen("jobs:analysis") == 0
    listed = (await client.get(f"/api/clips/{clip.id}/exports")).json()
    assert [e["id"] for e in listed] == [export["id"]]
    # Not rendered yet, so nothing to download.
    assert (await client.get(f"/api/exports/{export['id']}/video")).status_code == 404


async def test_unknown_clip_or_export_is_404(client):
    assert (await client.post(f"/api/clips/{uuid4()}/exports")).status_code == 404
    assert (await client.get(f"/api/exports/{uuid4()}/subtitles")).status_code == 404


def probe(path: Path) -> dict:
    out = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_streams",
            "-show_format",
            str(path),
        ],
        check=True,
        capture_output=True,
    ).stdout
    return json.loads(out)


def _has_libass() -> bool:
    filters = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True)
    return " subtitles " in filters.stdout


@pytest.mark.skipif(
    not _has_libass(), reason="host ffmpeg built without libass (worker image has it)"
)
async def test_real_render_cuts_crops_captions_and_mixes(tmp_path):
    source = make_video(tmp_path / "source.mp4", 1280, 720, seconds=8)
    music = tmp_path / "beat.mp3"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=220:duration=2",
         str(music)],
        check=True,
    )  # fmt: skip
    edl = Edl(
        ranges=[TimeSpan(start=1, end=3), TimeSpan(start=5, end=6.5)],
        captions=Captions(
            words=[
                Word(text="testing", start=1.2, end=1.8),
                Word(text="captions", start=5.1, end=5.9),
            ],
            style=CaptionStyle.BOXED,
        ),
        overlays=[Overlay(text="Hook line", start=0, end=2)],
        music=Music(file="x-beat.mp3", volume=0.3, duck=True),
    )
    progress = []

    async def report(fraction):
        progress.append(fraction)

    with ThreadPoolExecutor(1) as executor:
        renderer = FfmpegRendererAdapter(asyncio.Semaphore(1), executor, FONTS)
        await renderer.render(
            plan_render(edl, 1280, 720),
            source,
            music,
            tmp_path / "out.mp4",
            tmp_path / "out.srt",
            report,
        )

    info = probe(tmp_path / "out.mp4")
    video = next(s for s in info["streams"] if s["codec_type"] == "video")
    assert (video["width"], video["height"], video["codec_name"]) == (1080, 1920, "h264")
    assert any(s["codec_type"] == "audio" for s in info["streams"])
    assert float(info["format"]["duration"]) == pytest.approx(3.5, abs=0.15)
    assert "00:00:02,100 --> " in (tmp_path / "out.srt").read_text()  # 5.1 s → 2.1 s output
    assert progress and max(progress) <= 1.0
    assert not list(tmp_path.glob("*.ass")) and not list(tmp_path.glob("*.partial.*"))
