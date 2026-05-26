import base64
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

    # Public CDN bucket — a SEPARATE S3/R2 bucket (own credentials) that holds
    # only world-readable assets (user avatars). The private bucket above is
    # never made public; avatars live here because they render as direct
    # <img src>. When unset, public assets fall back to the private bucket.
    cdn_s3_bucket: str = ""
    cdn_s3_region: str = ""
    cdn_s3_access_key_id: str = ""
    cdn_s3_secret_access_key: str = ""
    cdn_s3_endpoint: str = ""

    usage_enabled: bool = False
    max_threads_per_project: int = 50
    file_revisions_max: int = 200

    # Compute-worker dispatch endpoint (pythonOCC + FEM + CAM + topo subprocess).
    pyworker_url: str = "http://localhost:8090"
    step_max_bytes: int = 200_000_000
    git_inline_max_bytes: int = 1_048_576
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
    # Cloud beta: when True billing is disabled server-side and the frontend
    # renders payment controls as visibly greyed-out. Set KERF_CLOUD_BETA=true
    # on the server; the value is mirrored to the frontend via /api/config.
    cloud_beta: bool = False
    cloud_paystack_secret_key: str = ""
    cloud_paystack_public_key: str = ""
    cloud_paystack_webhook_secret: str = ""
    cloud_fx_base_currency: str = "USD"
    cloud_fx_settlement_currency: str = "ZAR"
    cloud_fx_refresh_url: str = "https://api.exchangerate.host/latest?base=USD&symbols=ZAR"
    cloud_fx_spread_pct: float = 1.5
    cloud_pricing_token_markup_pct: float = 20.0
    cloud_pricing_gpu_markup_pct: float = 20.0
    cloud_pricing_storage_usd_per_gb_month: float = 0.20
    cloud_pricing_free_storage_mb: int = 50
    cloud_git_prefix: str = "git"
    cloud_github_client_id: str = ""
    cloud_github_client_secret: str = ""
    cloud_github_redirect_url: str = "http://localhost:8080/auth/github/callback"
    # GitHub App fields (repo-connect / installation token flow).
    # Leave empty to disable; the app degrades gracefully when unset.
    cloud_github_app_id: str = ""
    cloud_github_app_slug: str = ""
    cloud_github_private_key_b64: str = ""

    # GitLab OAuth App fields (repo-mirror flow via GitLabProvider).
    # Leave empty to disable; GitLabProvider.is_configured() gates on these.
    # cloud_gitlab_host: override when using a self-hosted GitLab instance;
    #   defaults to https://gitlab.com when empty.
    cloud_gitlab_app_id: str = ""
    cloud_gitlab_app_secret: str = ""
    cloud_gitlab_host: str = ""

    @property
    def github_private_key_pem(self) -> str:
        """Decode the base64 private key. Returns '' if unset."""
        raw = self.cloud_github_private_key_b64.strip()
        if not raw:
            return ""
        try:
            return base64.b64decode(raw).decode()
        except Exception:
            return ""

    # ---------------------------------------------------------------------------
    # Transactional email — pluggable provider + credentials.
    # email_provider: "smtp" (self-host default, zero-vendor) | "resend" | "ses".
    #   New providers slot in via kerf_cloud.email.providers (add to
    #   _VALID_PROVIDERS + a _send_<name>); no other code changes needed.
    # Our hosted cloud runs Resend today (EMAIL_PROVIDER=resend in the deploy
    #   env); the planned migration to SES is a pure env flip — set
    #   EMAIL_PROVIDER=ses + the ses_* fields, no code change.
    # email_from: default From address, e.g. "Kerf <noreply@kerf.sh>"
    # ---------------------------------------------------------------------------
    email_provider: str = "smtp"
    email_from: str = ""
    # SMTP (self-host / generic). STARTTLS is always negotiated; username and
    # password are optional for open relays.
    smtp_host: str = ""
    smtp_port: int = 0
    smtp_username: str = ""
    smtp_password: str = ""
    # Resend (current hosted provider).
    resend_api_key: str = ""
    # Amazon SES (planned hosted migration).
    ses_region: str = ""
    ses_access_key_id: str = ""
    ses_secret_access_key: str = ""

    # LLM prompt-caching controls.
    # When True (default), the Anthropic provider attaches cache_control
    # breakpoints to the system-prompt block and the tools block so that
    # repeated conversation turns reuse the cached prefix.  Set to False to
    # disable without restarting if cost-tracking or debugging is needed.
    anthropic_prompt_cache: bool = True

    @model_validator(mode="after")
    def _enforce_prod_secrets(self):
        """Refuse to start in production with dev-default secrets."""
        if self.env.lower() not in ("local", "dev", "development", "test"):
            _DEV_JWT = "dev-secret-change-in-production"
            _DEV_PEPPER = "dev-pepper"
            if self.jwt_secret == _DEV_JWT or self.password_pepper == _DEV_PEPPER:
                raise RuntimeError(
                    f"FATAL: Running in env={self.env!r} with dev-default secrets. "
                    "Set JWT_SECRET and PASSWORD_PEPPER to production values."
                )
        return self

    @model_validator(mode="after")
    def _enforce_cloud_disables_local_mode(self):
        if self.cloud_enabled and self.local_mode:
            self.local_mode = False
        return self

    @model_validator(mode="after")
    def _s3_env_aliases(self):
        # Storage secrets are provisioned/staged as KERF_STORAGE_S3_*
        # (Tigris/S3 convention), but the code reads s3_* (env S3_*). Map the
        # former onto the latter when the canonical var is unset.
        _aliases = {
            "s3_bucket": "KERF_STORAGE_S3_BUCKET",
            "s3_region": "KERF_STORAGE_S3_REGION",
            "s3_access_key_id": "KERF_STORAGE_S3_ACCESS_KEY",
            "s3_secret_access_key": "KERF_STORAGE_S3_SECRET_KEY",
            "s3_endpoint": "KERF_STORAGE_S3_ENDPOINT",
            "cdn_s3_bucket": "KERF_STORAGE_CDN_BUCKET",
            "cdn_s3_region": "KERF_STORAGE_CDN_REGION",
            "cdn_s3_access_key_id": "KERF_STORAGE_CDN_ACCESS_KEY",
            "cdn_s3_secret_access_key": "KERF_STORAGE_CDN_SECRET_KEY",
            "cdn_s3_endpoint": "KERF_STORAGE_CDN_ENDPOINT",
        }
        for field, env_name in _aliases.items():
            if not getattr(self, field):
                val = os.environ.get(env_name, "")
                if val:
                    setattr(self, field, val)
        return self

    @model_validator(mode="after")
    def _google_client_id_single_source(self):
        # The Google OAuth client ID is a public value the frontend needs
        # at build time (VITE_GOOGLE_CLIENT_ID). Rather than duplicate it,
        # the backend falls back to that same var when GOOGLE_CLIENT_ID is
        # unset — one value to configure.
        if not self.google_client_id:
            self.google_client_id = os.environ.get("VITE_GOOGLE_CLIENT_ID", "")
        return self

    @classmethod
    def load(cls, config_path: str = "") -> "Settings":
        """Load a Settings instance.

        ``config_path`` is currently unused (we read environment variables and
        the .env file); accepted for API compatibility with future TOML
        support and for use by ``kerf_core.app.create_app(config_path=...)``.
        """
        if config_path:
            os.environ.setdefault("KERF_CONFIG", config_path)
        return cls()


# Public alias — kerf-core's contract expects ``Config``.
Config = Settings


def is_production_env(env: str) -> bool:
    """Return True when *env* is not a recognised dev/test environment.

    Dev-safe values: "local", "dev", "development", "test".
    Any other value (e.g. "production", "staging", "prod") is treated as
    production so that the fail-closed secret checks fire.
    """
    return env.lower() not in ("local", "dev", "development", "test")


@lru_cache
def get_settings() -> Settings:
    return Settings()
