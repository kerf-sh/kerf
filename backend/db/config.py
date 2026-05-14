import os
from functools import lru_cache
from urllib.parse import urlparse

from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix='KERF_', env_file='.env', env_file_encoding='utf-8')

    database_url: str = "postgres://postgres:postgres@localhost:5432/kerf"
    db_max_conns: int = 10
    db_min_conns: int = 1
    db_max_conn_lifetime_minutes: int = 60
    db_max_conn_idle_time_minutes: int = 30


@lru_cache
def get_database_settings() -> DatabaseSettings:
    return DatabaseSettings()


def get_database_url() -> str:
    settings = get_database_settings()
    return settings.database_url


database_url = get_database_url()


class DatabaseURL:
    def __init__(self, url: str):
        self.raw = url
        parsed = urlparse(url)
        self.scheme = parsed.scheme
        self.username = parsed.username or ""
        self.password = parsed.password or ""
        self.host = parsed.hostname or ""
        self.port = parsed.port or 5432
        self.database = parsed.path.lstrip("/") or ""
        self.query = parsed.query

    def __str__(self) -> str:
        return self.raw
