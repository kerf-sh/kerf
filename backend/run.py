#!/usr/bin/env python3
import os
import sys
import asyncio
import signal
import logging
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def load_env():
    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ.setdefault(key.strip(), value.strip())


async def run_migrations(database_url: str):
    from db.migrations.runner import run_migrations as do_migrate
    await do_migrate(database_url)


def main():
    load_env()

    from config import get_settings
    settings = get_settings()

    database_url = os.getenv("DATABASE_URL", settings.database_url)

    logger.info("Running migrations...")
    asyncio.run(run_migrations(database_url))

    import uvicorn

    shutdown_event = asyncio.Event()

    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}")
        shutdown_event.set()

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    config = uvicorn.Config(
        "main:app",
        host="0.0.0.0",
        port=int(settings.port),
        log_level="info",
        timeout_graceful_shutdown=30,
        reload=False,
    )
    server = uvicorn.Server(config)

    logger.info(f"Starting server on port {settings.port}...")
    asyncio.run(server.serve())


if __name__ == "__main__":
    main()
