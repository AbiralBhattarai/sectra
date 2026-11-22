from uuid import uuid4

import httpx
import pytest

from src.adapters.output.persistence.postgres_clip_repository import PostgresClipRepository
from src.adapters.output.persistence.postgres_video_repository import PostgresVideoRepository
from src.api_main import create_app
from src.config.settings import Settings
from src.domain.enums.video_file_enum import VideoFile
from src.domain.models.video import Video
from tests.conftest import TEST_DATABASE_URL, TEST_REDIS_URL
from tests.unit.test_postgres_clip_repository import make_clip
from tests.unit.transcript_builders import evenly, transcript


@pytest.fixture
async def client(pg_sessionmaker, redis, tmp_path):
    settings = Settings(database_url=TEST_DATABASE_URL, redis_url=TEST_REDIS_URL, data_dir=tmp_path)
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


async def test_list_and_get_clips(client, pg_sessionmaker):
    video = Video(title="talk")
    await PostgresVideoRepository(pg_sessionmaker).add(video)
    clips = [make_clip(video, 0, 40), make_clip(video, 30, 80)]
    await PostgresClipRepository(pg_sessionmaker).replace_for_video(video.id, clips)

    listed = (await client.get(f"/api/videos/{video.id}/clips")).json()
    assert [c["score"] for c in listed] == [80, 40]
    assert "edl" not in listed[0]

    detail = (await client.get(f"/api/clips/{clips[0].id}")).json()
    assert detail["edl"]["aspect"] == "9:16"
    assert detail["edl"]["ranges"] == [{"start": 0.0, "end": 20.0}]


async def test_missing_video_or_clip_is_404(client):
    assert (await client.get(f"/api/videos/{uuid4()}/clips")).status_code == 404
    assert (await client.get(f"/api/clips/{uuid4()}")).status_code == 404


async def test_update_edl_saves_and_moves_bounds(client, pg_sessionmaker):
    video = Video(title="talk", duration=120)
    await PostgresVideoRepository(pg_sessionmaker).add(video)
    clip = make_clip(video, 30, 80)
    await PostgresClipRepository(pg_sessionmaker).replace_for_video(video.id, [clip])
    edl = clip.edl.model_dump(mode="json")
    edl["ranges"] = [{"start": 28, "end": 35}, {"start": 40, "end": 52}]
    edl["aspect"] = "1:1"
    edl["crop"] = {"x": 0.3, "y": 0.5, "scale": 1.5}
    edl["captions"]["style"] = "boxed"

    response = await client.put(f"/api/clips/{clip.id}", json={"edl": edl})

    assert response.status_code == 200
    saved = (await client.get(f"/api/clips/{clip.id}")).json()
    assert (saved["start"], saved["end"]) == (28, 52)
    assert saved["edl"]["ranges"] == edl["ranges"]
    assert saved["edl"]["aspect"] == "1:1"
    assert saved["edl"]["crop"]["scale"] == 1.5
    assert saved["edl"]["captions"]["style"] == "boxed"


async def test_update_rejects_unrenderable_edits(client, pg_sessionmaker):
    video = Video(title="talk", duration=60)
    await PostgresVideoRepository(pg_sessionmaker).add(video)
    clip = make_clip(video, 10, 80)
    await PostgresClipRepository(pg_sessionmaker).replace_for_video(video.id, [clip])
    edl = clip.edl.model_dump(mode="json")

    edl["ranges"] = [{"start": 50, "end": 70}]
    assert (await client.put(f"/api/clips/{clip.id}", json={"edl": edl})).status_code == 422

    edl["ranges"] = [{"start": 10, "end": 20}]
    edl["captions"]["style"] = "comic-sans"
    assert (await client.put(f"/api/clips/{clip.id}", json={"edl": edl})).status_code == 422


async def test_music_and_overlays_round_trip(client, pg_sessionmaker):
    video = Video(title="talk", duration=120)
    await PostgresVideoRepository(pg_sessionmaker).add(video)
    clip = make_clip(video, 30, 80)
    await PostgresClipRepository(pg_sessionmaker).replace_for_video(video.id, [clip])
    upload = await client.post("/api/music/upload", params={"filename": "beat.mp3"}, content=b"ID3")
    assert upload.status_code == 201
    track = upload.json()
    listed = (await client.get("/api/music")).json()
    assert track["file"] in [t["file"] for t in listed]
    assert next(t for t in listed if t["file"] == track["file"])["default"] is False
    assert (await client.get(f"/api/music/{track['file']}")).content == b"ID3"

    edl = clip.edl.model_dump(mode="json")
    edl["music"] = {"file": track["file"], "volume": 0.3, "duck": False}
    edl["overlays"] = [
        {"text": "Wait for it", "start": 0, "end": 3, "x": 0.5, "y": 0.1, "style": "label"}
    ]
    saved = (await client.put(f"/api/clips/{clip.id}", json={"edl": edl})).json()["edl"]
    assert saved["music"] == edl["music"]
    assert saved["overlays"][0]["style"] == "label"

    edl["music"]["file"] = "deadbeef-gone.mp3"
    response = await client.put(f"/api/clips/{clip.id}", json={"edl": edl})
    assert response.status_code == 422
    assert "not found" in response.json()["detail"]

    edl["music"]["file"] = "../secrets.mp3"
    assert (await client.put(f"/api/clips/{clip.id}", json={"edl": edl})).status_code == 422


async def test_caption_and_zooms_round_trip(client, pg_sessionmaker):
    video = Video(title="talk", duration=120)
    await PostgresVideoRepository(pg_sessionmaker).add(video)
    clip = make_clip(video, 30, 80)
    await PostgresClipRepository(pg_sessionmaker).replace_for_video(video.id, [clip])
    edl = clip.edl.model_dump(mode="json")
    edl["zooms"] = [{"start": 30, "end": 32, "scale": 1.2, "ramp": 1}]

    body = {"edl": edl, "caption": " He said WHAT #fyp "}
    assert (await client.put(f"/api/clips/{clip.id}", json=body)).status_code == 200
    saved = (await client.get(f"/api/clips/{clip.id}")).json()
    assert saved["caption"] == "He said WHAT #fyp"
    assert saved["edl"]["zooms"] == edl["zooms"]

    # Leaving the caption out keeps it.
    assert (await client.put(f"/api/clips/{clip.id}", json={"edl": edl})).status_code == 200
    assert (await client.get(f"/api/clips/{clip.id}")).json()["caption"] == "He said WHAT #fyp"


async def test_auto_zoom_generates_without_saving(client, pg_sessionmaker, tmp_path):
    video = Video(title="talk", duration=200)
    await PostgresVideoRepository(pg_sessionmaker).add(video)
    clip = make_clip(video, 30, 80)
    await PostgresClipRepository(pg_sessionmaker).replace_for_video(video.id, [clip])
    folder = tmp_path / "videos" / str(video.id)
    folder.mkdir(parents=True)
    (folder / VideoFile.TRANSCRIPT.value).write_text(transcript(evenly(20)).model_dump_json())

    response = await client.post(
        f"/api/clips/{clip.id}/auto-zoom", json={"ranges": [{"start": 30, "end": 60}]}
    )

    assert response.status_code == 200
    zooms = response.json()
    assert zooms[0]["start"] == 30 and zooms[0]["ramp"] > 0
    assert (await client.get(f"/api/clips/{clip.id}")).json()["edl"]["zooms"] == []
    missing = await client.post(
        f"/api/clips/{uuid4()}/auto-zoom", json={"ranges": [{"start": 0, "end": 1}]}
    )
    assert missing.status_code == 404


async def test_post_queues_a_render_and_reports_its_status(client, pg_sessionmaker, redis):
    video = Video(title="talk", duration=200)
    await PostgresVideoRepository(pg_sessionmaker).add(video)
    clip = make_clip(video, 0, 40)
    await PostgresClipRepository(pg_sessionmaker).replace_for_video(video.id, [clip])

    assert (await client.get(f"/api/clips/{clip.id}/post")).status_code == 204
    posted = await client.post(f"/api/clips/{clip.id}/post")
    assert posted.status_code == 202
    body = posted.json()
    assert body["platforms"] == ["youtube", "tiktok", "instagram", "x"]
    assert body["in_outbox"] is False and body["export"]["status"] == "queued"
    assert len(await redis.xrange("jobs:render")) == 1

    status = (await client.get(f"/api/clips/{clip.id}/post")).json()
    assert status["export"]["id"] == body["export"]["id"]
