"""
S3GitStorer — bulk-sync storage backend for S3-backed bare git repos.

This module provides a storer that syncs an entire bare git repository to/from
S3 using boto3, rather than implementing the per-object pygit2 OdbBackend
interface. The design is:

- clone_to_local: downloads all S3 keys under the prefix into a local bare repo.
- push_from_local: uploads all local files to S3, packs first via git gc, uploads
  objects/ before refs to maintain consistency, then cleans up orphan S3 keys.

Concurrent pushes are NOT serialized at the storer level — callers must hold a
DB advisory lock or similar external coordination. (Future: conditional put with
If-None-Match on a refs marker file.)

Pack files are uploaded BEFORE refs to ensure consistency. The best-effort
orphan cleanup after push leaves a short window where old packs could be
referenced by in-flight clones; in production a TTL/grace period or S3
lifecycle rules should be used.
"""

from __future__ import annotations

import logging
import os
import subprocess

import pygit2

logger = logging.getLogger(__name__)


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

    def _list_s3_keys(self) -> list[str]:
        keys = []
        prefix_with_slash = f"{self._prefix}/"
        continuation_token = None
        while True:
            kwargs = {"Bucket": self.bucket, "Prefix": prefix_with_slash}
            if continuation_token:
                kwargs["ContinuationToken"] = continuation_token
            response = self.s3.client.list_objects_v2(**kwargs)
            contents = response.get("Contents", [])
            for obj in contents:
                keys.append(obj["Key"])
            continuation_token = response.get("NextContinuationToken")
            if not continuation_token:
                break
        return keys

    def clone_to_local(self, local_dir: str) -> None:
        os.makedirs(local_dir, exist_ok=True)

        s3_keys = self._list_s3_keys()

        if not s3_keys:
            if os.listdir(local_dir):
                logger.warning(
                    "clone_to_local: no S3 keys found but local_dir is not empty; "
                    "skipping bare repo init"
                )
            else:
                pygit2.init_repository(local_dir, bare=True)
            return

        prefix_with_slash = f"{self._prefix}/"
        for key in s3_keys:
            rel_path = key[len(prefix_with_slash):]
            local_path = os.path.join(local_dir, rel_path)
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            data = self.s3.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()
            with open(local_path, "wb") as f:
                f.write(data)

        for d in ("refs/heads", "refs/tags", "objects/info", "objects/pack"):
            os.makedirs(os.path.join(local_dir, d), exist_ok=True)

    def push_from_local(self, local_dir: str) -> None:
        try:
            subprocess.run(
                ["git", "-C", local_dir, "gc", "--aggressive", "--prune=now"],
                check=True,
                capture_output=True,
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.warning("git gc failed or git not present; skipping repack")

        all_files: list[str] = []
        for root, _dirs, files in os.walk(local_dir):
            for fname in files:
                full_path = os.path.join(root, fname)
                rel_path = os.path.relpath(full_path, local_dir)
                all_files.append(rel_path)

        under_objects = [f for f in all_files if f.startswith("objects" + os.sep) or f == "objects"]
        under_objects.sort()
        rest = [f for f in all_files if f not in under_objects]
        ordered = under_objects + rest

        new_s3_keys: set[str] = set()
        for rel_path in ordered:
            s3_key = self._s3_key(rel_path)
            new_s3_keys.add(s3_key)
            local_path = os.path.join(local_dir, rel_path)
            with open(local_path, "rb") as f:
                data = f.read()
            self.s3.client.put_object(Bucket=self.bucket, Key=s3_key, Body=data)

        current_keys = set(self._list_s3_keys())
        orphans = current_keys - new_s3_keys
        for key in orphans:
            try:
                self.s3.client.delete_object(Bucket=self.bucket, Key=key)
            except Exception as e:
                logger.warning("Failed to delete orphan S3 key %s: %s", key, e)

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
