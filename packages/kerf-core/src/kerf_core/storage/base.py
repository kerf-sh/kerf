from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import IO, AsyncIterator, Optional, Any


@dataclass
class PutResult:
    key: str
    size: int
    content_type: str


class Storage(ABC):
    @abstractmethod
    async def put(
        self, key: str, body: IO[bytes], content_type: str, size: int
    ) -> PutResult: ...

    @abstractmethod
    async def get(self, key: str) -> tuple[IO[bytes], str]: ...

    @abstractmethod
    async def delete(self, key: str) -> None: ...

    @abstractmethod
    async def signed_url(self, key: str, ttl_seconds: int) -> str: ...

    @abstractmethod
    def public_url(self, key: str, updated_at: datetime | None = None) -> str: ...

    async def put_public(
        self, key: str, body: IO[bytes], content_type: str, size: int
    ) -> PutResult:
        """Write a world-readable asset (e.g. avatars).

        Backends with a dedicated public bucket override this to target it;
        the default delegates to ``put`` so local / single-bucket setups work
        unchanged.
        """
        return await self.put(key, body, content_type, size)

    async def delete_public(self, key: str) -> None:
        """Delete an object written via ``put_public``. Defaults to ``delete``."""
        await self.delete(key)

    @abstractmethod
    async def put_chunk(
        self,
        upload_key: str,
        chunk_index: int,
        body: IO[bytes],
        *,
        conn: Optional[Any] = None,
        session_id: Optional[Any] = None,
    ) -> None: ...

    @abstractmethod
    async def list_chunks(self, upload_key: str) -> list[int]: ...

    @abstractmethod
    async def concat_chunks_to(
        self,
        upload_key: str,
        dst_key: str,
        *,
        conn: Optional[Any] = None,
        session_id: Optional[Any] = None,
    ) -> int: ...

    @abstractmethod
    async def delete_upload(self, upload_key: str) -> None: ...

    @abstractmethod
    async def delete_prefix(self, prefix: str) -> int:
        """Delete all objects whose key starts with *prefix*.

        Returns the number of objects deleted.  Implementations must be
        best-effort: they should NOT raise on individual object failures but
        may raise if the listing itself fails.
        """
        ...


# Public alias used by kerf_core.plugin.PluginContext type annotation.
StorageBackend = Storage
