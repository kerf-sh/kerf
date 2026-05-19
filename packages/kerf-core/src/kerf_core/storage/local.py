import asyncio
import io
import logging
import mimetypes
import os
import shutil
import tempfile
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import IO

from .base import PutResult, Storage

logger = logging.getLogger(__name__)

CHUNK_DIR = "_uploads"


class LocalStorage(Storage):
    def __init__(self, root: str, cdn_url: str = ""):
        self.root = Path(root).resolve()
        self.cdn_url = cdn_url.rstrip("/") if cdn_url else ""
        self.root.mkdir(parents=True, exist_ok=True)

    def _safe_path(self, key: str) -> Path:
        clean = os.path.normpath("/" + key.lstrip("/"))
        if clean == "/" or clean.startswith(".."):
            raise ValueError(f"Invalid key: {key}")
        full = self.root / clean.lstrip("/")
        resolved = full.resolve()
        if not str(resolved).startswith(str(self.root) + os.sep) and resolved != self.root:
            raise ValueError(f"Path traversal detected: {key}")
        return full

    def _chunk_dir(self, upload_key: str) -> Path:
        if not upload_key or any(c in upload_key for c in "/\\"):
            raise ValueError(f"Invalid upload key: {upload_key}")
        return self.root / CHUNK_DIR / upload_key

    async def put(
        self, key: str, body: IO[bytes], content_type: str, size: int
    ) -> PutResult:
        dst = self._safe_path(key)
        dst.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.NamedTemporaryFile(
            dir=dst.parent, delete=False, prefix=".upload-"
        ) as tmp:
            tmp_path = tmp.name
            written = 0
            while chunk := body.read(65536):
                tmp.write(chunk)
                written += len(chunk)
            tmp.close()

        os.rename(tmp_path, str(dst))

        if not content_type:
            content_type = self._guess_content_type(key)

        return PutResult(key=key, size=written, content_type=content_type)

    async def get(self, key: str) -> tuple[IO[bytes], str]:
        src = self._safe_path(key)
        return open(src, "rb"), self._guess_content_type(key)

    async def delete(self, key: str) -> None:
        src = self._safe_path(key)
        try:
            src.unlink()
        except FileNotFoundError:
            pass

    async def signed_url(self, key: str, ttl_seconds: int) -> str:
        return ""

    def public_url(self, key: str, updated_at: datetime | None = None) -> str:
        base = "/api/blobs/" + self._escape_key(key)
        if self.cdn_url:
            base = self.cdn_url + "/" + self._escape_key(key)
        if updated_at:
            base += f"?v={int(updated_at.timestamp())}"
        return base

    async def put_chunk(
        self, upload_key: str, chunk_index: int, body: IO[bytes]
    ) -> None:
        if chunk_index < 0:
            raise ValueError("Negative chunk index")

        dir_path = self._chunk_dir(upload_key)
        dir_path.mkdir(parents=True, exist_ok=True)

        dst = dir_path / f"{chunk_index}.bin"
        with tempfile.NamedTemporaryFile(
            dir=dir_path, delete=False, prefix=".chunk-"
        ) as tmp:
            tmp_path = tmp.name
            while chunk := body.read(65536):
                tmp.write(chunk)
            tmp.close()

        os.rename(tmp_path, str(dst))

    async def list_chunks(self, upload_key: str) -> list[int]:
        dir_path = self._chunk_dir(upload_key)
        if not dir_path.exists():
            return []

        indices = []
        for entry in dir_path.iterdir():
            if entry.is_file() and entry.suffix == ".bin":
                try:
                    idx = int(entry.stem)
                    indices.append(idx)
                except ValueError:
                    continue
        return sorted(indices)

    async def concat_chunks_to(self, upload_key: str, dst_key: str) -> int:
        indices = await self.list_chunks(upload_key)
        if not indices:
            raise ValueError(f"No chunks for upload {upload_key}")

        dst = self._safe_path(dst_key)
        dst.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.NamedTemporaryFile(
            dir=dst.parent, delete=False, prefix=".upload-"
        ) as tmp:
            tmp_path = tmp.name
            total = 0
            for idx in indices:
                chunk_path = self._chunk_dir(upload_key) / f"{idx}.bin"
                with open(chunk_path, "rb") as src:
                    written = shutil.copyfileobj(src, tmp, length=65536)
                total += chunk_path.stat().st_size
            tmp.close()

        os.rename(tmp_path, str(dst))
        return total

    async def delete_prefix(self, prefix: str) -> int:
        """Delete all files under *prefix* by walking the local root directory."""
        clean = prefix.lstrip("/")
        target = (self.root / clean).resolve()
        # Safety: target must be inside root.
        if not str(target).startswith(str(self.root)):
            raise ValueError(f"delete_prefix: prefix escapes root: {prefix!r}")

        deleted = 0
        if target.is_dir():
            for entry in list(target.rglob("*")):
                if entry.is_file():
                    try:
                        entry.unlink()
                        deleted += 1
                    except OSError:
                        pass
            shutil.rmtree(target, ignore_errors=True)
        elif target.is_file():
            try:
                target.unlink()
                deleted = 1
            except OSError:
                pass
        return deleted

    async def delete_upload(self, upload_key: str) -> None:
        dir_path = self._chunk_dir(upload_key)
        shutil.rmtree(dir_path, ignore_errors=True)

    def _escape_key(self, key: str) -> str:
        parts = key.strip("/").split("/")
        return "/".join(urllib.parse.quote(p, safe="") for p in parts)

    def _guess_content_type(self, key: str) -> str:
        ext = os.path.splitext(key)[1].lower()
        if ext in (".step", ".stp"):
            return "model/step"
        ct, _ = mimetypes.guess_type(key)
        return ct or "application/octet-stream"
