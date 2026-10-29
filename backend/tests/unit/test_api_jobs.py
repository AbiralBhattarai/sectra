from uuid import uuid4

import httpx
import pytest

from src.api_main import create_app
from src.config.settings import Settings
from tests.conftest import TEST_DATABASE_URL, TEST_REDIS_URL


@pytest.fixture
async def client(pg_sessionmaker, redis):
    app = create_app(Settings(database_url=TEST_DATABASE_URL, redis_url=TEST_REDIS_URL))
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


async def test_healthz(client):
    response = await client.get("/healthz")
    assert response.json() == {"status": "ok"}


async def test_submit_ping_queues_job_on_stream(client, redis):
    response = await client.post("/api/jobs/ping", json={"steps": 3})
    assert response.status_code == 202
    job = response.json()
    assert job["status"] == "queued"

    entries = await redis.xrange("jobs:analysis")
    assert [fields["job_id"] for _, fields in entries] == [job["id"]]

    fetched = await client.get(f"/api/jobs/{job['id']}")
    assert fetched.json()["id"] == job["id"]


async def test_unknown_job_is_404(client):
    assert (await client.get(f"/api/jobs/{uuid4()}")).status_code == 404


async def test_invalid_ping_steps_is_422(client):
    assert (await client.post("/api/jobs/ping", json={"steps": 0})).status_code == 422
