from .base import Storage, PutResult
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
        )

    if backend in ("local", "filesystem"):
        return LocalStorage(root=local_storage_path, cdn_url=cdn_base_url)

    raise ValueError(f"Unknown storage backend: {backend} (expected local|s3|filesystem)")


__all__ = ["Storage", "PutResult", "LocalStorage", "S3Storage", "create_storage"]
