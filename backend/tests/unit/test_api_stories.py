from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from src.adapters.output.persistence.postgres_job_repository import PostgresJobRepository
from src.adapters.output.persistence.postgres_video_repository import PostgresVideoRepository
from src.api_main import create_app
from src.config.settings import Settings
from src.domain.enums.job_type_enum import JobType
from src.domain.enums.video_kind_enum import VideoKind
from src.domain.models.job import Job
from src.domain.models.story import StorySpec
from src.domain.models.video import Video
from tests.conftest import TEST_DATABASE_URL, TEST_REDIS_URL

CHARACTERS = Path(__file__).resolve().parents[3] / "assets" / "characters"


@pytest.fixture
async def client(pg_sessionmaker, redis, tmp_path):
    settings = Settings(
        database_url=TEST_DATABASE_URL,
        redis_url=TEST_REDIS_URL,
        data_dir=tmp_path,
        characters_dir=CHARACTERS,
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


async def test_create_story_lists_it_as_a_story_and_queues_narration(client, redis):
    response = await client.post(
        "/api/stories",
        json={"text": "It all started at brunch. Then chaos.", "character": "girl"},
    )
    assert response.status_code == 202
    story = response.json()
    assert story["kind"] == "story" and story["title"] == "It all started at brunch."
    assert story["story"]["character"] == "girl" and story["story"]["background_mode"] == "black"

    [listed] = (await client.get("/api/videos")).json()
    assert listed["current_job"]["type"] == "narrate"
    assert len(await redis.xrange("jobs:analysis")) == 1


async def test_bad_story_is_422(client):
    assert (await client.post("/api/stories", json={"text": "hi", "voice": "x"})).status_code == 422
    assert (await client.post("/api/stories", json={"text": ""})).status_code == 422


async def test_options_and_character_layers(client):
    options = (await client.get("/api/stories/options")).json()
    assert {"id": "guy", "label": "Guy (fade + beard)", "voice": "am_michael"} in options[
        "characters"
    ]
    assert any(v["id"] == "af_heart" for v in options["voices"])

    layer = await client.get("/api/characters/guy/mouth/D.svg")
    assert layer.status_code == 200 and layer.headers["content-type"] == "image/svg+xml"
    assert (await client.get("/api/characters/guy/../../secret")).status_code == 404
    assert (await client.get("/api/characters/wizard/blink.svg")).status_code == 404


async def test_background_library_endpoints(client, redis, tmp_path):
    response = await client.post(
        "/api/backgrounds", json={"url": "https://youtu.be/parkour", "category": "minecraft"}
    )
    assert response.status_code == 202 and response.json()["type"] == "background"
    assert len(await redis.xrange("jobs:ingest")) == 1

    clip = tmp_path / "backgrounds" / "roblox" / "0123abcd-obby.mp4"
    clip.parent.mkdir(parents=True)
    clip.write_bytes(b"mp4")
    library = (await client.get("/api/backgrounds")).json()
    assert [b["ref"] for b in library["ready"]] == ["roblox/0123abcd-obby.mp4"]
    assert [p["category"] for p in library["pending"]] == ["minecraft"]

    assert (await client.get("/api/backgrounds/roblox/0123abcd-obby.mp4")).content == b"mp4"
    assert (await client.delete("/api/backgrounds/roblox/0123abcd-obby.mp4")).status_code == 204
    assert (await client.get("/api/backgrounds")).json()["ready"] == []


async def test_story_round_trips_through_postgres(pg_sessionmaker):
    repo = PostgresVideoRepository(pg_sessionmaker)
    video = Video(title="t", kind=VideoKind.STORY, story=StorySpec(text="Once.", character="girl"))
    await repo.add(video)
    video.story = video.story.model_copy(update={"narration": "Once.", "caption": "c"})
    await repo.save(video)
    assert await repo.get(video.id) == video
    plain = Video(title="podcast")
    await repo.add(plain)
    assert (await repo.get(plain.id)).kind is VideoKind.SOURCE


async def test_jobs_listed_by_type_newest_first(pg_sessionmaker):
    jobs = PostgresJobRepository(pg_sessionmaker)
    now = datetime.now(UTC)
    first = Job(type=JobType.BACKGROUND, created_at=now - timedelta(seconds=1))
    second = Job(type=JobType.BACKGROUND, created_at=now)
    await jobs.add(first)
    await jobs.add(second)
    await jobs.add(Job(type=JobType.PING))
    assert [j.id for j in await jobs.list_by_type(JobType.BACKGROUND)] == [second.id, first.id]
