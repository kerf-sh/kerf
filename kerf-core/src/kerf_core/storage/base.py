from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import IO, AsyncIterator


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

    @abstractmethod
    async def put_chunk(
        self, upload_key: str, chunk_index: int, body: IO[bytes]
    ) -> None: ...

    @abstractmethod
    async def list_chunks(self, upload_key: str) -> list[int]: ...

    @abstractmethod
    async def concat_chunks_to(self, upload_key: str, dst_key: str) -> int: ...

    @abstractmethod
    async def delete_upload(self, upload_key: str) -> None: ...


# Public alias used by kerf_core.plugin.PluginContext type annotation.
StorageBackend = Storage
