import os

DEFAULT_URL = "https://kerf.app"


def load_token() -> str:
    token = os.environ.get("KERF_API_TOKEN", "").strip()
    if not token:
        raise RuntimeError(
            "KERF_API_TOKEN is not set. "
            "Generate one from workspace settings and export it."
        )
    return token


def load_url() -> str:
    return os.environ.get("KERF_API_URL", DEFAULT_URL).rstrip("/")
