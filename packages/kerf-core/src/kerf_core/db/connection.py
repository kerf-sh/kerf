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


async def create_pool_from_config(config) -> asyncpg.Pool:
    """Open and cache an asyncpg pool using a kerf_core Config/Settings instance.

    Pool size is resolved from (in priority order):
    1. ``KERF_DB_MAX_CONNS`` environment variable
    2. ``config.db_max_conns`` attribute (if present)
    3. Default of 10
    """
    import os as _os
    global _pool
    if not getattr(config, "database_url", ""):
        raise ValueError("Config.database_url is required but not set")

    try:
        max_size = int(_os.environ.get("KERF_DB_MAX_CONNS", "") or getattr(config, "db_max_conns", 10))
    except (ValueError, TypeError):
        max_size = 10

    pool = await asyncpg.create_pool(
        config.database_url,
        min_size=2,
        max_size=max_size,
        command_timeout=60,
        timeout=10,
    )
    _pool = pool
    return pool
