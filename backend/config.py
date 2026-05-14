import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT_ENV = str(Path(__file__).resolve().parent.parent / ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_REPO_ROOT_ENV, env_file_encoding='utf-8', extra='ignore')
    env: str = "local"
    port: str = "8080"
    database_url: str = "postgres://postgres:postgres@localhost:5432/kerf"
    jwt_secret: str = "dev-secret-change-in-production"
    jwt_access_ttl_minutes: int = 15
    jwt_refresh_ttl_days: int = 30
    password_pepper: str = "dev-pepper"
    cors_origin: str = "http://localhost:5173"
    local_mode: bool = True
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_url: str = "http://localhost:8080/auth/google/callback"
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    moonshot_api_key: str = ""
    gemini_api_key: str = ""
    default_model: str = "claude-opus-4-7"

    storage_backend: str = "local"
    local_storage_path: str = "./.kerf-storage"
    filesystem_root: str = "~/kerf-projects"
    s3_bucket: str = ""
    s3_region: str = ""
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    s3_endpoint: str = ""
    s3_public_url_base: str = ""
    cdn_base_url: str = ""

    usage_enabled: bool = False
    max_threads_per_project: int = 50
    file_revisions_max: int = 200
    step_max_bytes: int = 200_000_000
    upload_chunk_size: int = 5_242_880
    upload_session_ttl_hours: int = 24

    step_tessellate_workers: int = 2
    step_tessellate_timeout_sec: int = 300
    fem_workers: int = 2
    fem_timeout_sec: int = 600
    sim_workers: int = 2
    sim_timeout_sec: int = 600

    system_user_email: str = ""
    system_user_name: str = ""
    system_user_password: str = ""

    cloud_enabled: bool = False
    cloud_paystack_secret_key: str = ""
    cloud_paystack_public_key: str = ""
    cloud_paystack_webhook_secret: str = ""
    cloud_fx_base_currency: str = "USD"
    cloud_fx_settlement_currency: str = "ZAR"
    cloud_fx_refresh_url: str = "https://api.exchangerate.host/latest?base=USD&symbols=ZAR"
    cloud_fx_spread_pct: float = 1.5
    cloud_pricing_token_markup_pct: float = 20.0
    cloud_pricing_storage_usd_per_gb_month: float = 0.20
    cloud_pricing_free_storage_mb: int = 50
    cloud_git_prefix: str = "git"
    cloud_github_client_id: str = ""
    cloud_github_client_secret: str = ""
    cloud_github_redirect_url: str = "http://localhost:8080/auth/github/callback"

    @model_validator(mode="after")
    def _enforce_cloud_disables_local_mode(self):
        if self.cloud_enabled and self.local_mode:
            self.local_mode = False
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
