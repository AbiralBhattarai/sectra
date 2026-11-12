from uuid import uuid4

import httpx
import pytest

from src.adapters.output.persistence.postgres_clip_repository import PostgresClipRepository
from src.adapters.output.persistence.postgres_video_repository import PostgresVideoRepository
from src.api_main import create_app
from src.config.settings import Settings
from src.domain.enums.video_kind_enum import VideoKind
from src.domain.models.video import Video
from tests.conftest import TEST_DATABASE_URL, TEST_REDIS_URL
from tests.unit.test_postgres_clip_repository import make_clip


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
    segment = detail["edl"]["segments"][0]
    assert (segment["kind"], segment["start"], segment["end"]) == ("video", 0, 20)
    assert detail["revision"] == 0


async def test_missing_video_or_clip_is_404(client):
    assert (await client.get(f"/api/videos/{uuid4()}/clips")).status_code == 404
    assert (await client.get(f"/api/clips/{uuid4()}")).status_code == 404


async def test_update_edl_saves_and_moves_bounds(client, pg_sessionmaker):
    video = Video(title="talk", duration=120)
    await PostgresVideoRepository(pg_sessionmaker).add(video)
    clip = make_clip(video, 30, 80)
    await PostgresClipRepository(pg_sessionmaker).replace_for_video(video.id, [clip])
    edl = clip.edl.model_dump(mode="json")
    edl["segments"] = [
        {"id": "b", "start": 40, "end": 52},
        {"id": "a", "start": 28, "end": 35, "speed": 2},
    ]
    edl["aspect"] = "1:1"
    edl["crop"] = {"x": 0.3, "y": 0.5, "scale": 1.5}
    edl["captions"]["style"] = "boxed"

    response = await client.put(f"/api/clips/{clip.id}", json={"edl": edl})

    assert response.status_code == 200, response.text
    saved = (await client.get(f"/api/clips/{clip.id}")).json()
    assert (saved["start"], saved["end"]) == (28, 52)
    assert [(g["id"], g["speed"]) for g in saved["edl"]["segments"]] == [("b", 1), ("a", 2)]
    assert saved["revision"] == 1
    assert saved["edl"]["aspect"] == "1:1"
    assert saved["edl"]["crop"]["scale"] == 1.5
    assert saved["edl"]["captions"]["style"] == "boxed"


async def test_update_rejects_unrenderable_edits(client, pg_sessionmaker):
    video = Video(title="talk", duration=60)
    await PostgresVideoRepository(pg_sessionmaker).add(video)
    clip = make_clip(video, 10, 80)
    await PostgresClipRepository(pg_sessionmaker).replace_for_video(video.id, [clip])
    edl = clip.edl.model_dump(mode="json")

    edl["segments"] = [{"start": 50, "end": 70}]
    assert (await client.put(f"/api/clips/{clip.id}", json={"edl": edl})).status_code == 422

    edl["segments"] = [{"start": 10, "end": 20}]
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


async def make(pg_sessionmaker, duration=120):
    video = Video(title="talk", duration=duration)
    await PostgresVideoRepository(pg_sessionmaker).add(video)
    clip = make_clip(video, 30, 80)
    await PostgresClipRepository(pg_sessionmaker).replace_for_video(video.id, [clip])
    return clip


async def test_edits_are_revisions_that_undo_and_redo(client, pg_sessionmaker):
    clip = await make(pg_sessionmaker)
    url = f"/api/clips/{clip.id}"
    first = clip.edl.segments[0].id

    split = await client.post(f"{url}/edits", json={"commands": [{"op": "split", "at": 5}]})
    assert split.status_code == 200
    body = split.json()
    assert body["revision"] == 1 and len(body["edl"]["segments"]) == 2
    assert (body["can_undo"], body["can_redo"]) == (True, False)
    second = body["edl"]["segments"][1]["id"]
    commands = [
        {"op": "set_transition", "segment_id": second, "type": "fadeblack", "duration": 0.5},
        {"op": "update_segment", "segment_ids": [first], "speed": 2, "color_preset": "bw"},
    ]
    edited = (
        await client.post(f"{url}/edits", json={"commands": commands, "base_revision": 1})
    ).json()
    assert edited["revision"] == 2

    timeline = (await client.get(f"{url}/timeline")).json()
    assert (timeline["can_undo"], timeline["can_redo"]) == (True, False)
    assert [(s["output_start"], s["output_end"]) for s in timeline["segments"]] == [
        (0, 2.5),
        (2, 17),
    ]
    assert timeline["segments"][0]["text"] == "hi"
    assert timeline["duration"] == 17

    assert (await client.post(f"{url}/undo")).json()["revision"] == 1
    assert (await client.post(f"{url}/undo")).json()["edl"]["segments"][0]["end"] == 50
    assert (await client.post(f"{url}/undo")).status_code == 422  # nothing left
    redone = (await client.post(f"{url}/redo", json={"actor": "mcp"})).json()
    assert (redone["revision"], redone["can_undo"], redone["can_redo"]) == (1, True, True)
    history = (await client.get(f"{url}/history")).json()
    assert [(h["revision"], h["label"]) for h in history] == [
        (0, "Original"),
        (1, "split"),
        (2, "set_transition, update_segment"),
    ]

    # A new edit after undoing drops the redo branch.
    await client.post(f"{url}/edits", json={"commands": [{"op": "add_marker", "time": 1}]})
    assert [h["revision"] for h in (await client.get(f"{url}/history")).json()] == [0, 1, 2]
    assert (await client.get(f"{url}/timeline")).json()["can_redo"] is False


async def test_stale_revisions_conflict_and_dry_runs_save_nothing(client, pg_sessionmaker):
    clip = await make(pg_sessionmaker)
    url = f"/api/clips/{clip.id}/edits"
    marker = {"op": "add_marker", "time": 1}
    stale = await client.post(url, json={"commands": [marker], "base_revision": 3})
    assert stale.status_code == 409

    preview = (await client.post(url, json={"commands": [marker], "dry_run": True})).json()
    assert len(preview["edl"]["markers"]) == 1
    saved = (await client.get(f"/api/clips/{clip.id}")).json()
    assert (saved["revision"], saved["edl"]["markers"]) == (0, [])


async def test_invalid_commands_name_the_failing_one(client, pg_sessionmaker):
    clip = await make(pg_sessionmaker)
    response = await client.post(
        f"/api/clips/{clip.id}/edits",
        json={"commands": [{"op": "split", "at": 3}, {"op": "delete", "segment_ids": ["nope"]}]},
    )
    assert response.status_code == 422
    assert response.json()["detail"].startswith("Command 2 (delete): No segment 'nope'")
    assert (
        await client.post(f"/api/clips/{clip.id}/edits", json={"commands": [{"op": "fly"}]})
    ).status_code == 422


async def test_command_schema_lists_every_op(client):
    schema = (await client.get("/api/edit-commands/schema")).json()
    ops = schema["discriminator"]["mapping"]
    assert {"split", "trim", "set_transition", "add_broll", "freeze_frame"} <= set(ops)
    assert "Output time to cut at" in str(schema["$defs"]["Split"])


async def test_images_and_asset_videos_can_be_edited_in(client, pg_sessionmaker, tmp_path):
    clip = await make(pg_sessionmaker)
    upload = await client.post(
        "/api/images/upload", params={"filename": "My Logo.PNG"}, content=b"\x89PNG"
    )
    assert upload.status_code == 201
    image = upload.json()["file"]
    assert image.endswith("-My-Logo.png")
    assert [i["file"] for i in (await client.get("/api/images")).json()] == [image]
    assert (await client.get(f"/api/images/{image}")).content == b"\x89PNG"
    assert (
        await client.post("/api/images/upload", params={"filename": "x.gif"}, content=b"")
    ).status_code == 422

    asset = Video(title="b-roll", kind=VideoKind.ASSET, duration=10)
    await PostgresVideoRepository(pg_sessionmaker).add(asset)
    (tmp_path / "videos" / str(asset.id)).mkdir(parents=True)
    (tmp_path / "videos" / str(asset.id) / "source.mp4").write_bytes(b"")
    assets = (await client.get("/api/videos", params={"kind": "asset"})).json()
    assert [(v["id"], v["kind"]) for v in assets] == [(str(asset.id), "asset")]

    commands = [
        {"op": "insert_image", "image": image, "duration": 2, "at_index": 0},
        {"op": "insert", "media": str(asset.id), "start": 1, "end": 4},
        {"op": "add_broll", "media": str(asset.id), "start": 0, "duration": 2},
    ]
    edited = await client.post(f"/api/clips/{clip.id}/edits", json={"commands": commands})
    assert edited.status_code == 200, edited.text
    assert [s["kind"] for s in edited.json()["edl"]["segments"]] == ["image", "video", "video"]

    missing = [{"op": "insert_image", "image": "deadbeef-gone.png"}]
    response = await client.post(f"/api/clips/{clip.id}/edits", json={"commands": missing})
    assert response.status_code == 422 and "not found" in response.json()["detail"]
