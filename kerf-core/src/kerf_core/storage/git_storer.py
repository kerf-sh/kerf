"""
S3GitStorer — bulk-sync storage backend for S3-backed bare git repos.

This module syncs an entire bare git repository to/from S3 using boto3,
rather than implementing the per-object pygit2 OdbBackend interface. The
design is:

- clone_to_local: downloads every S3 key under the prefix into a local
  bare repo. If the prefix is empty the local dir is initialized as a
  fresh bare repo.
- push_from_local: repacks the local repo (best effort), then uploads
  pack/loose objects FIRST and refs LAST so a concurrent reader never
  sees a ref pointing at an object that hasn't been uploaded yet. Orphan
  keys (no longer referenced by the local repo) are batch-deleted after
  the upload completes.

Concurrency
-----------
A single sentinel object at `<prefix>/_marker` is used for optimistic
concurrency control. push_from_local reads the marker ETag, performs
all uploads, then writes a fresh marker conditional on `If-Match` of
the original ETag. If two pushers race, the loser sees PreconditionFailed
and the caller must retry (or abort) with fresher data.

For higher-level coordination (e.g. only allow one push per project)
the caller should still hold a DB advisory lock — the marker only
protects against torn refs, not against losing commits when two pushers
both append divergent histories.

OSS / local-install path
------------------------
This storer is only constructed when the storage backend is S3. The
LocalStorage backend keeps the on-disk filesystem layout that
plain `git` and pygit2 already understand — there is nothing to "store"
through this class for local installs.
"""

from __future__ import annotations

import logging
import os
import subprocess
import time
from typing import Iterable

import pygit2

logger = logging.getLogger(__name__)

# Maximum keys per S3 DeleteObjects call (S3 API hard limit).
_BATCH_DELETE_MAX = 1000

# Sentinel object whose ETag is used for optimistic concurrency.
_MARKER_NAME = "_marker"


class StorerConcurrencyError(RuntimeError):
    """Raised when a push lost an optimistic-concurrency race."""


class S3GitStorer:
    def __init__(self, s3, bucket: str, prefix: str) -> None:
        self.s3 = s3
        self.bucket = bucket
        self._prefix = prefix.rstrip("/")

    @classmethod
    def from_s3storage(cls, s3storage, repo_prefix: str) -> "S3GitStorer":
        return cls(s3storage, s3storage.bucket, repo_prefix)

    def _s3_key(self, rel_path: str) -> str:
        return f"{self._prefix}/{rel_path}".replace("\\", "/")

    @property
    def _marker_key(self) -> str:
        return f"{self._prefix}/{_MARKER_NAME}"

    def _list_s3_keys(self) -> list[str]:
        keys: list[str] = []
        prefix_with_slash = f"{self._prefix}/"
        continuation_token = None
        while True:
            kwargs = {"Bucket": self.bucket, "Prefix": prefix_with_slash}
            if continuation_token:
                kwargs["ContinuationToken"] = continuation_token
            response = self.s3.client.list_objects_v2(**kwargs)
            for obj in response.get("Contents", []):
                keys.append(obj["Key"])
            continuation_token = response.get("NextContinuationToken")
            if not continuation_token:
                break
        return keys

    def _read_marker_etag(self) -> str | None:
        try:
            head = self.s3.client.head_object(Bucket=self.bucket, Key=self._marker_key)
            return head.get("ETag")
        except Exception as e:
            msg = str(e)
            if "NoSuchKey" in msg or "Not Found" in msg or "404" in msg:
                return None
            raise

    def clone_to_local(self, local_dir: str) -> None:
        t0 = time.monotonic()
        os.makedirs(local_dir, exist_ok=True)

        s3_keys = self._list_s3_keys()

        if not s3_keys:
            if os.listdir(local_dir):
                logger.warning(
                    "S3GitStorer.clone_to_local: prefix=%s empty but local_dir=%s not empty; "
                    "skipping bare repo init",
                    self._prefix, local_dir,
                )
            else:
                pygit2.init_repository(local_dir, bare=True)
                logger.info(
                    "S3GitStorer.clone_to_local: prefix=%s empty; initialized fresh bare repo at %s",
                    self._prefix, local_dir,
                )
            return

        prefix_with_slash = f"{self._prefix}/"
        downloaded = 0
        total_bytes = 0
        for key in s3_keys:
            rel_path = key[len(prefix_with_slash):]
            if rel_path == _MARKER_NAME:
                continue
            local_path = os.path.join(local_dir, rel_path)
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            data = self.s3.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()
            with open(local_path, "wb") as f:
                f.write(data)
            downloaded += 1
            total_bytes += len(data)

        for d in ("refs/heads", "refs/tags", "objects/info", "objects/pack"):
            os.makedirs(os.path.join(local_dir, d), exist_ok=True)

        logger.info(
            "S3GitStorer.clone_to_local: prefix=%s files=%d bytes=%d elapsed=%.3fs",
            self._prefix, downloaded, total_bytes, time.monotonic() - t0,
        )

    def _split_pack_loose_refs(self, all_files: list[str]) -> tuple[list[str], list[str], list[str]]:
        pack: list[str] = []
        loose: list[str] = []
        refs: list[str] = []
        for rel in all_files:
            parts = rel.split(os.sep)
            if parts[0] == "objects":
                if len(parts) >= 2 and parts[1] == "pack":
                    pack.append(rel)
                else:
                    loose.append(rel)
            elif parts[0] == "refs" or rel in ("HEAD", "packed-refs"):
                refs.append(rel)
            else:
                refs.append(rel)
        pack.sort()
        loose.sort()
        refs.sort()
        return pack, loose, refs

    def push_from_local(self, local_dir: str) -> None:
        t0 = time.monotonic()
        try:
            subprocess.run(
                ["git", "-C", local_dir, "gc", "--aggressive", "--prune=now"],
                check=True,
                capture_output=True,
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.warning(
                "S3GitStorer.push_from_local: git gc failed or git not present at %s; "
                "skipping repack",
                local_dir,
            )

        original_marker_etag = self._read_marker_etag()

        all_files: list[str] = []
        for root, _dirs, files in os.walk(local_dir):
            for fname in files:
                full_path = os.path.join(root, fname)
                rel_path = os.path.relpath(full_path, local_dir)
                all_files.append(rel_path)

        pack_files, loose_files, ref_files = self._split_pack_loose_refs(all_files)

        new_s3_keys: set[str] = set()
        bytes_uploaded = 0

        def _upload_group(rel_paths: Iterable[str]) -> None:
            nonlocal bytes_uploaded
            for rel_path in rel_paths:
                s3_key = self._s3_key(rel_path)
                new_s3_keys.add(s3_key)
                local_path = os.path.join(local_dir, rel_path)
                with open(local_path, "rb") as f:
                    data = f.read()
                self.s3.client.put_object(Bucket=self.bucket, Key=s3_key, Body=data)
                bytes_uploaded += len(data)

        _upload_group(pack_files)
        _upload_group(loose_files)
        _upload_group(ref_files)

        marker_put_kwargs = {
            "Bucket": self.bucket,
            "Key": self._marker_key,
            "Body": str(int(time.time() * 1000)).encode("ascii"),
        }
        if original_marker_etag is None:
            marker_put_kwargs["IfNoneMatch"] = "*"
        else:
            marker_put_kwargs["IfMatch"] = original_marker_etag
        try:
            self.s3.client.put_object(**marker_put_kwargs)
        except Exception as e:
            if "PreconditionFailed" in str(e):
                raise StorerConcurrencyError(
                    f"push lost concurrency race on {self._marker_key}: another writer "
                    f"updated the repo since this push started"
                ) from e
            raise
        new_s3_keys.add(self._marker_key)

        current_keys = set(self._list_s3_keys())
        orphans = sorted(current_keys - new_s3_keys)
        deleted = self._batch_delete(orphans)

        logger.info(
            "S3GitStorer.push_from_local: prefix=%s pack=%d loose=%d refs=%d "
            "bytes=%d orphans=%d/%d elapsed=%.3fs",
            self._prefix, len(pack_files), len(loose_files), len(ref_files),
            bytes_uploaded, deleted, len(orphans), time.monotonic() - t0,
        )

    def _batch_delete(self, keys: list[str]) -> int:
        if not keys:
            return 0
        deleted = 0
        for i in range(0, len(keys), _BATCH_DELETE_MAX):
            batch = keys[i:i + _BATCH_DELETE_MAX]
            try:
                response = self.s3.client.delete_objects(
                    Bucket=self.bucket,
                    Delete={"Objects": [{"Key": k} for k in batch]},
                )
                deleted += len(response.get("Deleted", []))
                for err in response.get("Errors", []):
                    logger.warning(
                        "S3GitStorer._batch_delete: prefix=%s key=%s code=%s msg=%s",
                        self._prefix, err.get("Key"), err.get("Code"), err.get("Message"),
                    )
            except Exception as e:
                logger.warning(
                    "S3GitStorer._batch_delete: batch failed (size=%d): %s",
                    len(batch), e,
                )
        return deleted

    def open_repo(self, local_dir: str) -> pygit2.Repository:
        if not os.path.isdir(local_dir):
            raise FileNotFoundError(
                f"{local_dir} does not exist as a directory. Call clone_to_local first."
            )
        try:
            return pygit2.Repository(local_dir)
        except Exception as e:
            raise FileNotFoundError(
                f"{local_dir} is not a git repository. Call clone_to_local first."
            ) from e
