from uuid import uuid4

import httpx
import pytest

from src.api_main import create_app
from src.config.settings import Settings
from tests.conftest import TEST_DATABASE_URL, TEST_REDIS_URL


@pytest.fixture
async def client(pg_sessionmaker, redis, tmp_path):
    settings = Settings(database_url=TEST_DATABASE_URL, redis_url=TEST_REDIS_URL, data_dir=tmp_path)
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


async def test_add_url_then_list(client, redis):
    response = await client.post("/api/videos", json={"url": "https://youtu.be/abc"})
    assert response.status_code == 202
    video = response.json()

    [listed] = (await client.get("/api/videos")).json()
    assert listed["id"] == video["id"]
    assert listed["status"] == "processing"
    assert listed["current_job"]["type"] == "ingest"
    assert len(await redis.xrange("jobs:analysis")) == 1


async def test_add_rejects_non_http_url(client):
    response = await client.post("/api/videos", json={"url": "file:///etc/passwd"})
    assert response.status_code == 422


async def test_upload_streams_body_to_disk(client, tmp_path):
    response = await client.post(
        "/api/videos/upload", params={"filename": "talk.mp4"}, content=b"0123456789"
    )
    assert response.status_code == 202
    video_id = response.json()["id"]
    assert (tmp_path / "videos" / video_id / "raw.mp4").read_bytes() == b"0123456789"


async def test_upload_rejects_unsupported_type(client):
    response = await client.post(
        "/api/videos/upload", params={"filename": "notes.txt"}, content=b"x"
    )
    assert response.status_code == 422


async def test_media_supports_range_requests(client, tmp_path):
    video_id = (await client.post("/api/videos", json={"url": "https://a.example"})).json()["id"]
    (tmp_path / "videos" / video_id).mkdir(parents=True, exist_ok=True)
    (tmp_path / "videos" / video_id / "source.mp4").write_bytes(b"0123456789")

    response = await client.get(
        f"/api/videos/{video_id}/media/source.mp4", headers={"Range": "bytes=2-5"}
    )

    assert response.status_code == 206
    assert response.content == b"2345"


async def test_unknown_media_file_name_is_rejected(client):
    video_id = (await client.post("/api/videos", json={"url": "https://a.example"})).json()["id"]
    response = await client.get(f"/api/videos/{video_id}/media/raw.mp4")
    assert response.status_code == 422


async def test_delete_then_404(client):
    video_id = (await client.post("/api/videos", json={"url": "https://a.example"})).json()["id"]
    assert (await client.delete(f"/api/videos/{video_id}")).status_code == 204
    assert (await client.get(f"/api/videos/{video_id}")).status_code == 404
    assert (await client.delete(f"/api/videos/{uuid4()}")).status_code == 404
