import base64
import hashlib
import io
import os
import random
import string
import urllib.parse
from datetime import datetime
from typing import IO


def _random_suffix() -> str:
    return "".join(random.choices(string.hexdigits.lower(), k=8))


class S3FileInfo:
    def __init__(self, name: str, size: int = 0, mod: datetime | None = None, is_dir: bool = False):
        self.name = name
        self.size = size
        self.mod = mod or datetime.now()
        self.is_dir = is_dir

    def mode(self) -> int:
        if self.is_dir:
            return 0o40755
        return 0o644

    def is_dir_(self) -> bool:
        return self.is_dir


class S3File:
    def __init__(
        self,
        fs: "S3Filesystem",
        key: str,
        name: str,
        buf: io.BytesIO | None = None,
        writable: bool = False,
        write_once: bool = False,
    ):
        self.fs = fs
        self.key = key
        self.name = name
        self.buf = buf or io.BytesIO()
        self.writable = writable
        self.write_once = write_once
        self.closed = False
        self.dirty = False
        self._lock = False

    def read(self, n: int = -1) -> bytes:
        if n == -1:
            data = self.buf.read()
        else:
            data = self.buf.read(n)
        return data

    def read_at(self, p: bytearray, off: int) -> int:
        if off < 0:
            raise ValueError("Negative offset")
        self.buf.seek(off)
        data = self.buf.read(len(p))
        p[:] = data
        return len(data)

    def write(self, p: bytes) -> int:
        if not self.writable:
            raise IOError("File not opened for write")
        n = self.buf.write(p)
        if n > 0:
            self.dirty = True
        return n

    def seek(self, offset: int, whence: int = 0) -> int:
        if whence == 0:
            abs_pos = offset
        elif whence == 1:
            abs_pos = self.buf.tell() + offset
        elif whence == 2:
            abs_pos = len(self.buf.getvalue()) + offset
        else:
            raise ValueError(f"Invalid whence: {whence}")
        if abs_pos < 0:
            raise ValueError("Negative seek")
        self.buf.seek(abs_pos)
        return abs_pos

    def truncate(self, size: int) -> None:
        if not self.writable:
            raise IOError("File not opened for write")
        current = self.buf.getvalue()
        if len(current) == size:
            return
        if len(current) > size:
            self.buf = io.BytesIO(current[:size])
        else:
            self.buf = io.BytesIO(current + b"\x00" * (size - len(current)))
        self.dirty = True

    def tell(self) -> int:
        return self.buf.tell()

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        if self.writable and self.dirty:
            self.fs._put_object(self.key, self.buf.getvalue(), self.write_once)

    def name(self) -> str:
        return self.name

    def isatty(self) -> bool:
        return False

    def flush(self) -> None:
        pass

    def lock(self) -> None:
        pass

    def unlock(self) -> None:
        pass


class S3Filesystem:
    CAPABILITIES = "write|read|seek|truncate"

    def __init__(self, client, bucket: str, root: str = ""):
        self.client = client
        self.bucket = bucket
        self.root = root.strip("/")

    def _key_for(self, path: str) -> str:
        path = path.lstrip("/")
        if self.root:
            return f"{self.root}/{path}"
        return path

    def _head(self, key: str) -> dict | None:
        try:
            return self.client.head_object(Bucket=self.bucket, Key=key)
        except Exception as e:
            if "NotFound" in str(e) or "NoSuchKey" in str(e):
                return None
            raise

    def _get(self, key: str) -> bytes:
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
            return response["Body"].read()
        except Exception as e:
            if "NotFound" in str(e) or "NoSuchKey" in str(e):
                raise FileNotFoundError(f"{key} not found")
            raise

    def _put_object(self, key: str, data: bytes, exclusive: bool = False) -> None:
        kwargs = {"Bucket": self.bucket, "Key": key, "Body": data}
        if exclusive:
            kwargs["IfNoneMatch"] = "*"
        try:
            self.client.put_object(**kwargs)
        except Exception as e:
            if exclusive and "PreconditionFailed" in str(e):
                raise FileExistsError(f"{key} already exists")
            raise

    def create(self, filename: str) -> S3File:
        return self.open_file(filename, os.O_RDWR | os.O_CREATE | os.O_TRUNC, 0o666)

    def open(self, filename: str) -> S3File:
        return self.open_file(filename, os.O_RDONLY, 0)

    def open_file(self, filename: str, flag: int, _mode: int) -> S3File:
        key = self._key_for(filename)
        want_read = (flag & os.O_WRONLY) == 0
        want_write = (flag & (os.O_WRONLY | os.O_RDWR)) != 0
        create = (flag & os.O_CREATE) != 0
        excl = (flag & os.O_EXCL) != 0
        trunc = (flag & os.O_TRUNC) != 0

        initial = b""
        need_seed = not trunc and (want_read or want_write)

        if not want_write and not create:
            need_seed = True

        if need_seed:
            try:
                initial = self._get(key)
            except FileNotFoundError:
                if not create:
                    raise
            except Exception:
                if not create:
                    raise

        return S3File(
            fs=self,
            key=key,
            name=filename,
            buf=io.BytesIO(initial),
            writable=want_write,
            write_once=create and excl,
        )

    def stat(self, filename: str) -> S3FileInfo:
        key = self._key_for(filename)
        head = self._head(key)
        if head is None:
            entries = self.read_dir(filename)
            if entries:
                return S3FileInfo(name=os.path.basename(filename.rstrip("/")), is_dir=True)
            raise FileNotFoundError(f"{filename} not found")

        size = head.get("ContentLength", 0) or 0
        mod = head.get("LastModified", datetime.now())
        return S3FileInfo(name=os.path.basename(filename), size=size, mod=mod)

    def rename(self, from_: str, to: str) -> None:
        src_key = self._key_for(from_)
        dst_key = self._key_for(to)
        if src_key == dst_key:
            return

        self.client.copy_object(
            Bucket=self.bucket,
            CopySource={"Bucket": self.bucket, "Key": src_key},
            Key=dst_key,
        )
        self.client.delete_object(Bucket=self.bucket, Key=src_key)

    def remove(self, filename: str) -> None:
        key = self._key_for(filename)
        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
        except Exception as e:
            if "NotFound" not in str(e) and "NoSuchKey" not in str(e):
                raise

    def join(self, *parts: str) -> str:
        return "/".join(p.strip("/") for p in parts if p)

    def read_dir(self, path: str) -> list[S3FileInfo]:
        prefix = self._key_for(path)
        if prefix and not prefix.endswith("/"):
            prefix += "/"

        try:
            response = self.client.list_objects_v2(
                Bucket=self.bucket, Prefix=prefix, Delimiter="/"
            )
        except Exception:
            return []

        infos = []
        for obj in response.get("Contents", []):
            key = obj["Key"]
            name = key[len(prefix) :].rstrip("/")
            if not name:
                continue
            infos.append(
                S3FileInfo(
                    name=name,
                    size=obj.get("Size", 0) or 0,
                    mod=obj.get("LastModified", datetime.now()),
                )
            )

        for prefix_resp in response.get("CommonPrefixes", []):
            p = prefix_resp.get("Prefix", "")
            name = p[len(prefix) :].rstrip("/")
            if name:
                infos.append(S3FileInfo(name=name, is_dir=True))

        return infos

    def mkdir_all(self, path: str, _mode: int) -> None:
        pass

    def temp_file(self, dir_: str, prefix: str) -> S3File:
        suffix = _random_suffix()
        name = self.join(dir_, f".tmp-{prefix}-{suffix}")
        return self.open_file(name, os.O_RDWR | os.O_CREATE | os.O_TRUNC, 0o600)

    def lstat(self, filename: str) -> S3FileInfo:
        return self.stat(filename)

    def symlink(self, src: str, dst: str) -> None:
        raise NotImplementedError("Symlinks not supported")

    def readlink(self, path: str) -> str:
        raise NotImplementedError("Symlinks not supported")

    def chroot(self, path: str) -> "S3Filesystem":
        sub = path.strip("/")
        new_root = self.root
        if sub:
            new_root = f"{new_root}/{sub}" if new_root else sub
        return S3Filesystem(self.client, self.bucket, new_root)

    def root_(self) -> str:
        return "/"

    def capabilities(self) -> str:
        return self.CAPABILITIES

    def delete_by_prefix(self, prefix: str) -> None:
        prefix = prefix.rstrip("/")
        if prefix:
            prefix += "/"

        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            objects = [{"Key": obj["Key"]} for obj in page.get("Contents", [])]
            if objects:
                self.client.delete_objects(Bucket=self.bucket, Delete={"Objects": objects})
            if not page.get("IsTruncated"):
                break

    def exists(self, prefix: str) -> bool:
        prefix = prefix.rstrip("/") + "/" if prefix else ""
        response = self.client.list_objects_v2(Bucket=self.bucket, Prefix=prefix, MaxKeys=1)
        return len(response.get("Contents", [])) > 0
