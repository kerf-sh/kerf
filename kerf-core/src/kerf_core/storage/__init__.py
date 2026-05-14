from typing import Optional

from .base import Storage, PutResult
from .factory import create_storage
from .git import S3Filesystem
from .local import LocalStorage
from .s3 import S3Storage

_storage: Optional[Storage] = None


def set_storage(storage: Storage) -> None:
    global _storage
    _storage = storage


def get_storage() -> Optional[Storage]:
    return _storage


def get_storage_required() -> Storage:
    if _storage is None:
        raise RuntimeError("Storage not initialized. Call set_storage() first.")
    return _storage


__all__ = ["Storage", "PutResult", "LocalStorage", "S3Storage", "S3Filesystem", "create_storage", "get_storage", "get_storage_required", "set_storage"]
