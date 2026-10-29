import os

import asyncpg
import pytest
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import create_async_engine

from src.adapters.output.persistence.db import create_sessionmaker
from src.adapters.output.persistence.models import Base

# Throwaway databases on the compose services (`docker compose up -d postgres redis`).
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL", "postgresql+asyncpg://sectra:sectra@localhost:5433/sectra_test"
)
TEST_REDIS_URL = os.getenv("TEST_REDIS_URL", "redis://localhost:6380/15")


async def _ensure_database(url: str) -> None:
    server_url, _, name = url.replace("postgresql+asyncpg", "postgresql").rpartition("/")
    conn = await asyncpg.connect(f"{server_url}/postgres")
    try:
        if not await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", name):
            await conn.execute(f'CREATE DATABASE "{name}"')
    finally:
        await conn.close()


@pytest.fixture(scope="session")
async def pg_engine():
    await _ensure_database(TEST_DATABASE_URL)
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def pg_sessionmaker(pg_engine):
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    async with pg_engine.begin() as conn:
        await conn.exec_driver_sql(f"TRUNCATE {tables}")
    return create_sessionmaker(pg_engine)


@pytest.fixture
async def redis():
    client = Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    await client.flushdb()
    yield client
    await client.flushdb()
    await client.aclose()
