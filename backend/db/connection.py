import asyncpg
from typing import Optional
from contextlib import asynccontextmanager

from .config import get_database_settings, DatabaseSettings


_pool: Optional[asyncpg.Pool] = None


async def create_pool(settings: Optional[DatabaseSettings] = None) -> asyncpg.Pool:
    global _pool
    if settings is None:
        settings = get_database_settings()

    dsn = settings.database_url

    pool = await asyncpg.create_pool(
        dsn,
        min_size=settings.db_min_conns,
        max_size=settings.db_max_conns,
        command_timeout=60,
        timeout=10,
    )

    _pool = pool
    return pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def get_pool() -> Optional[asyncpg.Pool]:
    return _pool


async def get_pool_required() -> asyncpg.Pool:
    pool = get_pool()
    if pool is None:
        raise RuntimeError("Database pool not initialized. Call create_pool() first.")
    return pool


@asynccontextmanager
async def acquire_connection():
    pool = await get_pool_required()
    async with pool.acquire() as conn:
        yield conn


@asynccontextmanager
async def transaction():
    pool = await get_pool_required()
    async with pool.acquire() as conn:
        async with conn.transaction():
            yield conn
