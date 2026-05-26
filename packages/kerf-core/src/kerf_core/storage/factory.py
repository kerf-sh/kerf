from .base import Storage, PutResult
from .git_storer import (
    ProjectRepoLocation,
    project_git_prefix,
    resolve_project_repo,
)
from .local import LocalStorage
from .s3 import S3Storage


def create_storage(
    backend: str = "",
    s3_bucket: str = "",
    s3_region: str = "",
    s3_access_key_id: str = "",
    s3_secret_access_key: str = "",
    s3_endpoint: str = "",
    s3_public_url_base: str = "",
    cdn_base_url: str = "",
    cdn_s3_bucket: str = "",
    cdn_s3_region: str = "",
    cdn_s3_access_key_id: str = "",
    cdn_s3_secret_access_key: str = "",
    cdn_s3_endpoint: str = "",
    local_storage_path: str = "./.kerf-storage",
) -> Storage:
    backend = backend or ("s3" if s3_bucket else "local")

    if backend == "s3":
        if not s3_bucket:
            raise ValueError("S3_BUCKET is required when STORAGE_BACKEND=s3")
        return S3Storage(
            bucket=s3_bucket,
            region=s3_region,
            access_key_id=s3_access_key_id,
            secret_access_key=s3_secret_access_key,
            endpoint=s3_endpoint,
            public_url_base=s3_public_url_base,
            cdn_url=cdn_base_url,
            public_bucket=cdn_s3_bucket,
            public_region=cdn_s3_region,
            public_access_key_id=cdn_s3_access_key_id,
            public_secret_access_key=cdn_s3_secret_access_key,
            public_endpoint=cdn_s3_endpoint,
        )

    if backend in ("local", "filesystem"):
        return LocalStorage(root=local_storage_path, cdn_url=cdn_base_url)

    raise ValueError(f"Unknown storage backend: {backend} (expected local|s3|filesystem)")


__all__ = [
    "Storage",
    "PutResult",
    "LocalStorage",
    "S3Storage",
    "create_storage",
    "ProjectRepoLocation",
    "project_git_prefix",
    "resolve_project_repo",
]
