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
        public_bucket: str = "",
        public_region: str = "",
        public_access_key_id: str = "",
        public_secret_access_key: str = "",
        public_endpoint: str = "",
    ):
        self.bucket = bucket
        self.public_url_base = public_url_base.rstrip("/") if public_url_base else ""
        self.cdn_url = cdn_url.rstrip("/") if cdn_url else ""

        self.client = self._build_client(
            region, access_key_id, secret_access_key, endpoint
        )

        # Optional dedicated public bucket (own credentials). Holds only
        # world-readable assets served via the CDN/public URL. When unset,
        # public writes fall back to the private bucket + client.
        self.public_bucket = public_bucket
        if public_bucket:
            self.public_client = self._build_client(
                public_region or region,
                public_access_key_id,
                public_secret_access_key,
                public_endpoint or endpoint,
            )
        else:
            self.public_client = self.client

        self._multipart: dict[str, dict] = {}

    @staticmethod
    def _build_client(region, access_key_id, secret_access_key, endpoint):
        client_kwargs = {"region_name": region} if region else {}

        if access_key_id and secret_access_key:
            client_kwargs["aws_access_key_id"] = access_key_id
            client_kwargs["aws_secret_access_key"] = secret_access_key

        if endpoint:
            client_kwargs["endpoint_url"] = endpoint
            config = boto3.session.Config(s3={"addressing_style": "path"})
            client_kwargs["config"] = config

        return boto3.client("s3", **client_kwargs)

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

    async def put_public(
        self, key: str, body: IO[bytes], content_type: str, size: int
    ) -> PutResult:
        if not self.public_bucket:
            return await self.put(key, body, content_type, size)

        if not content_type:
            content_type = self._guess_content_type(key)
        content = await _run_sync(body.read) if hasattr(body, "read") else body

        put_kwargs = dict(
            Bucket=self.public_bucket,
            Key=key,
            Body=content,
            ContentType=content_type,
        )
        if size > 0:
            put_kwargs["ContentLength"] = size

        await _run_sync(self.public_client.put_object, **put_kwargs)
        return PutResult(key=key, size=size, content_type=content_type)

    async def delete_public(self, key: str) -> None:
        if not self.public_bucket:
            return await self.delete(key)
        await _run_sync(
            self.public_client.delete_object, Bucket=self.public_bucket, Key=key
        )

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
            host_bucket = self.public_bucket or self.bucket
            base = f"https://{host_bucket}.s3.amazonaws.com/{self._escape_key(key)}"

        if updated_at:
            base += f"?v={int(updated_at.timestamp())}"
        return base

    async def put_chunk(
        self,
        upload_key: str,
        chunk_index: int,
        body: IO[bytes],
        *,
        conn=None,
        session_id=None,
    ) -> None:
        if chunk_index < 0:
            raise ValueError("Negative chunk index")

        content = body.read() if hasattr(body, "read") else body
        part_number = chunk_index + 1

        if conn is not None and session_id is not None:
            # DB-backed path: safe under horizontal scale.
            from kerf_core.db.queries.upload_sessions import (
                init_s3_multipart,
                append_s3_part,
                get_s3_multipart_state,
            )
            state = await get_s3_multipart_state(conn, session_id)
            if state is None:
                temp_key = self._temp_key(upload_key)
                response = await _run_sync(
                    self.client.create_multipart_upload, Bucket=self.bucket, Key=temp_key
                )
                upload_id = response["UploadId"]
                await init_s3_multipart(conn, session_id, upload_id, temp_key)
                state = {"upload_id": upload_id, "temp_key": temp_key, "parts": []}

            part_response = await _run_sync(
                self.client.upload_part,
                Bucket=self.bucket,
                Key=state["temp_key"],
                UploadId=state["upload_id"],
                PartNumber=part_number,
                Body=content,
            )
            await append_s3_part(conn, session_id, part_number, part_response["ETag"])
        else:
            # Fallback: in-process dict (single-replica only).
            await self._ensure_multipart(upload_key)
            state = self._multipart[upload_key]
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

    async def concat_chunks_to(self, upload_key: str, dst_key: str, *, conn=None, session_id=None) -> int:
        if conn is not None and session_id is not None:
            # DB-backed path.
            from kerf_core.db.queries.upload_sessions import get_s3_multipart_state
            state_db = await get_s3_multipart_state(conn, session_id)
            if not state_db:
                raise ValueError(f"No DB multipart state for upload {upload_key}")
            parts = sorted(state_db["parts"], key=lambda p: p["PartNumber"])
            if not parts:
                raise ValueError(f"No parts uploaded for {upload_key}")
            temp_key = state_db["temp_key"]
            upload_id = state_db["upload_id"]
        else:
            # Fallback: in-process dict.
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

        if conn is None or session_id is None:
            self._multipart.pop(upload_key, None)
        return size

    async def delete_prefix(self, prefix: str) -> int:
        """Delete all objects under *prefix* using paginated ListObjectsV2."""
        deleted = 0
        continuation_token = None
        while True:
            kwargs: dict = {"Bucket": self.bucket, "Prefix": prefix, "MaxKeys": 1000}
            if continuation_token:
                kwargs["ContinuationToken"] = continuation_token

            page = await _run_sync(self.client.list_objects_v2, **kwargs)
            contents = page.get("Contents", [])

            if contents:
                objects = [{"Key": obj["Key"]} for obj in contents]
                await _run_sync(
                    self.client.delete_objects,
                    Bucket=self.bucket,
                    Delete={"Objects": objects, "Quiet": True},
                )
                deleted += len(objects)

            if not page.get("IsTruncated"):
                break
            continuation_token = page.get("NextContinuationToken")

        return deleted

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
