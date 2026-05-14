import asyncio
import boto3
import functools
import io
import logging
import mimetypes
from datetime import datetime
from typing import IO

from botocore.config import Config as BotoConfig

from .base import PutResult, Storage


async def _run_sync(func, /, *args, **kwargs):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, functools.partial(func, *args, **kwargs))

logger = logging.getLogger(__name__)

CHUNK_DIR = "_uploads"


class S3Storage(Storage):
    def __init__(
        self,
        bucket: str,
        region: str = "",
        access_key_id: str = "",
        secret_access_key: str = "",
        endpoint: str = "",
        public_url_base: str = "",
        cdn_url: str = "",
    ):
        self.bucket = bucket
        self.public_url_base = public_url_base.rstrip("/") if public_url_base else ""
        self.cdn_url = cdn_url.rstrip("/") if cdn_url else ""

        client_kwargs = {"region_name": region} if region else {}

        if access_key_id and secret_access_key:
            client_kwargs["aws_access_key_id"] = access_key_id
            client_kwargs["aws_secret_access_key"] = secret_access_key

        if endpoint:
            client_kwargs["endpoint_url"] = endpoint
            config = boto3.session.Config(s3={"addressing_style": "path"})
            client_kwargs["config"] = config

        self.client = boto3.client("s3", **client_kwargs)
        self._multipart: dict[str, dict] = {}

    def _temp_key(self, upload_key: str) -> str:
        return f"{CHUNK_DIR}/{upload_key}"

    async def put(
        self, key: str, body: IO[bytes], content_type: str, size: int
    ) -> PutResult:
        if not content_type:
            content_type = self._guess_content_type(key)

        content = await _run_sync(body.read) if hasattr(body, "read") else body

        put_kwargs = dict(
            Bucket=self.bucket,
            Key=key,
            Body=content,
            ContentType=content_type,
        )
        if size > 0:
            put_kwargs["ContentLength"] = size

        await _run_sync(self.client.put_object, **put_kwargs)

        return PutResult(key=key, size=size, content_type=content_type)

    async def get(self, key: str) -> tuple[io.BytesIO, str]:
        response = await _run_sync(self.client.get_object, Bucket=self.bucket, Key=key)
        body = await _run_sync(response["Body"].read)
        content_type = response.get("ContentType", self._guess_content_type(key))
        return io.BytesIO(body), content_type

    async def delete(self, key: str) -> None:
        await _run_sync(self.client.delete_object, Bucket=self.bucket, Key=key)

    async def signed_url(self, key: str, ttl_seconds: int = 900) -> str:
        if ttl_seconds <= 0:
            ttl_seconds = 900

        return await _run_sync(
            self.client.generate_presigned_url,
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=ttl_seconds,
        )

    def public_url(self, key: str, updated_at: datetime | None = None) -> str:
        if self.cdn_url:
            base = f"{self.cdn_url}/{self._escape_key(key)}"
        elif self.public_url_base:
            base = f"{self.public_url_base}/{self._escape_key(key)}"
        else:
            base = f"https://{self.bucket}.s3.amazonaws.com/{self._escape_key(key)}"

        if updated_at:
            base += f"?v={int(updated_at.timestamp())}"
        return base

    async def put_chunk(
        self, upload_key: str, chunk_index: int, body: IO[bytes]
    ) -> None:
        if chunk_index < 0:
            raise ValueError("Negative chunk index")

        await self._ensure_multipart(upload_key)

        state = self._multipart[upload_key]
        content = body.read() if hasattr(body, "read") else body

        part_number = chunk_index + 1
        response = await _run_sync(
            self.client.upload_part,
            Bucket=self.bucket,
            Key=state["dst_key"],
            UploadId=state["upload_id"],
            PartNumber=part_number,
            Body=content,
        )

        state["parts"][chunk_index] = {
            "ETag": response["ETag"],
            "PartNumber": part_number,
        }

    async def list_chunks(self, upload_key: str) -> list[int]:
        state = self._multipart.get(upload_key)
        if not state:
            return []
        return sorted(state["parts"].keys())

    async def concat_chunks_to(self, upload_key: str, dst_key: str) -> int:
        state = self._multipart.get(upload_key)
        if not state:
            raise ValueError(f"No multipart state for upload {upload_key}")

        indices = sorted(state["parts"].keys())
        if not indices:
            raise ValueError(f"No parts uploaded for {upload_key}")

        parts = [state["parts"][idx] for idx in indices]
        temp_key = state["dst_key"]
        upload_id = state["upload_id"]

        await _run_sync(
            self.client.complete_multipart_upload,
            Bucket=self.bucket,
            Key=temp_key,
            UploadId=upload_id,
            MultipartUpload={"Parts": parts},
        )

        copy_source = {"Bucket": self.bucket, "Key": temp_key}
        await _run_sync(
            self.client.copy_object,
            Bucket=self.bucket,
            Key=dst_key,
            CopySource=copy_source,
        )
        await _run_sync(self.client.delete_object, Bucket=self.bucket, Key=temp_key)

        head = await _run_sync(self.client.head_object, Bucket=self.bucket, Key=dst_key)
        size = head.get("ContentLength", 0)

        del self._multipart[upload_key]
        return size

    async def delete_upload(self, upload_key: str) -> None:
        state = self._multipart.get(upload_key)
        if not state:
            return

        try:
            await _run_sync(
                self.client.abort_multipart_upload,
                Bucket=self.bucket,
                Key=state["dst_key"],
                UploadId=state["upload_id"],
            )
        except Exception:
            pass

        del self._multipart[upload_key]

    async def _ensure_multipart(self, upload_key: str) -> None:
        if upload_key in self._multipart:
            return

        temp_key = self._temp_key(upload_key)
        response = await _run_sync(
            self.client.create_multipart_upload, Bucket=self.bucket, Key=temp_key
        )

        self._multipart[upload_key] = {
            "upload_id": response["UploadId"],
            "dst_key": temp_key,
            "parts": {},
        }

    def _escape_key(self, key: str) -> str:
        import urllib.parse

        parts = key.strip("/").split("/")
        return "/".join(urllib.parse.quote(p, safe="") for p in parts)

    def _guess_content_type(self, key: str) -> str:
        ext = key.split(".")[-1].lower() if "." in key else ""
        if ext in ("step", "stp"):
            return "model/step"
        ct, _ = mimetypes.guess_type(key)
        return ct or "application/octet-stream"
