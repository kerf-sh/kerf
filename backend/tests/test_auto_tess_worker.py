"""
Hermetic tests for the cloud-tier auto_tess STEP pre-tessellation worker.

These tests avoid real Postgres / pyworker / pythonOCC by injecting fake
collaborators. They exercise the worker's job lifecycle:

    queued → claim → fetch STEP from storage → tessellate →
    persist mesh blob + derived_artifact row → mark job done

and the failure / idempotency branches.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import os
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import pytest

from kerf_tess.worker import AutoTessWorker, _read_storage
from kerf_tess.specs import TessInputSpec


# --------------------------------------------------------------------------- fakes


class _FakeReader:
    def __init__(self, data: bytes) -> None:
        self._data = data
        self.closed = False

    def read(self) -> bytes:
        return self._data

    def close(self) -> None:
        self.closed = True


class _FakeStorage:
    def __init__(self) -> None:
        self.blobs: Dict[str, bytes] = {}
        self.put_calls: List[tuple] = []

    async def get(self, key: str):
        if key not in self.blobs:
            raise FileNotFoundError(key)
        return _FakeReader(self.blobs[key]), "model/step"

    async def put(self, key: str, body: io.BytesIO, content_type: str, size: int):
        self.put_calls.append((key, content_type, size))
        self.blobs[key] = body.read()


class _FakeDriver:
    def __init__(
        self,
        output: bytes = b"GLB-bytes",
        raise_exc: Optional[Exception] = None,
        delay: float = 0.0,
    ) -> None:
        self.output = output
        self.raise_exc = raise_exc
        self.delay = delay
        self.calls: List[tuple] = []

    async def tessellate(self, step_bytes: bytes, spec: TessInputSpec) -> bytes:
        self.calls.append((len(step_bytes), spec.to_dict()))
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.raise_exc:
            raise self.raise_exc
        return self.output


@dataclass
class _Row:
    data: Dict[str, Any]

    def __getitem__(self, k):
        return self.data[k]

    def get(self, k, default=None):
        return self.data.get(k, default)


@dataclass
class _StepJob:
    id: uuid.UUID
    file_id: uuid.UUID
    status: str = "queued"
    error: Optional[str] = None
    mesh_storage_key: Optional[str] = None
    content_sha256: Optional[str] = None
    input_spec: Optional[Dict] = None
    started_at: Any = None
    finished_at: Any = None
    created_at: int = 0  # monotonic order


@dataclass
class _File:
    id: uuid.UUID
    storage_key: Optional[str]
    deleted_at: Any = None
    mesh_storage_key: Optional[str] = None


@dataclass
class _DerivedArtifact:
    source_file_id: uuid.UUID
    content_sha256: str
    derived_kind: str
    payload: bytes
    last_accessed_at: int = 0


class _FakeConn:
    """Hand-rolled conn that interprets the small set of SQL fragments the worker emits."""

    def __init__(self, db: "_FakeDB") -> None:
        self.db = db

    # ---- transaction context

    def transaction(self):
        conn = self

        class _Tx:
            async def __aenter__(self_inner):
                return self_inner

            async def __aexit__(self_inner, exc_type, exc, tb):
                return False

        return _Tx()

    # ---- listener no-op

    async def add_listener(self, channel, callback):
        self.db.listeners.setdefault(channel, []).append(callback)

    async def remove_listener(self, channel, callback):
        pass

    # ---- query dispatch

    async def fetchrow(self, query: str, *args):
        q = " ".join(query.split())
        if "FROM step_tessellation_jobs j" in q and "FOR UPDATE OF j SKIP LOCKED" in q:
            return self._claim_job()
        if "FROM derived_artifacts" in q and "step_mesh" in q:
            return self._find_artifact(args)
        raise AssertionError(f"unexpected fetchrow query: {q[:120]}")

    async def execute(self, query: str, *args):
        q = " ".join(query.split())
        if q.startswith("UPDATE step_tessellation_jobs"):
            return self._update_job(q, args)
        if q.startswith("UPDATE files SET mesh_storage_key"):
            self.db.file_by_id(args[0]).mesh_storage_key = args[1]
            return "UPDATE 1"
        if q.startswith("UPDATE derived_artifacts SET last_accessed_at"):
            for a in self.db.artifacts:
                if str(a) == str(args[0]):
                    a.last_accessed_at += 1
            return "UPDATE 1"
        if "INSERT INTO derived_artifacts" in q:
            self._upsert_artifact(args)
            return "INSERT 1"
        if "pg_notify" in q:
            return "SELECT 1"
        raise AssertionError(f"unexpected execute query: {q[:120]}")

    # ---- helpers

    def _claim_job(self):
        queued = [
            j for j in self.db.jobs
            if j.status == "queued"
            and self.db.file_by_id(j.file_id).deleted_at is None
        ]
        if not queued:
            return None
        queued.sort(key=lambda j: j.created_at)
        return _Row({
            "id": queued[0].id,
            "file_id": queued[0].file_id,
            "project_id": uuid.uuid4(),
            "storage_key": self.db.file_by_id(queued[0].file_id).storage_key,
            "input_spec": queued[0].input_spec,
        })

    def _find_artifact(self, args):
        file_id, sha = args[0], args[1]
        for a in self.db.artifacts:
            if a.source_file_id == file_id and a.content_sha256 == sha and a.derived_kind == "step_mesh":
                return _Row({"id": uuid.uuid4()})
        return None

    def _update_job(self, q: str, args):
        job_id = args[0]
        job = next((j for j in self.db.jobs if j.id == job_id), None)
        if job is None:
            return "UPDATE 0"
        if "status='running'" in q:
            job.status = "running"
            job.started_at = "now"
            job.error = None
        elif "status='done'" in q:
            job.status = "done"
            job.mesh_storage_key = args[1]
            job.content_sha256 = args[2]
            job.finished_at = "now"
            job.error = None
        elif "status='error'" in q:
            job.status = "error"
            if len(args) > 1:
                job.error = args[1]
            else:
                # Inline literal — extract substring between first single-quoted error= clause.
                import re as _re
                m = _re.search(r"error\s*=\s*'([^']*)'", q)
                job.error = m.group(1) if m else "unknown"
            job.finished_at = "now"
        elif "status = 'queued'" in q and "WHERE status = 'running'" in q:
            # stuck-job recovery — no-op for tests
            pass
        return "UPDATE 1"

    def _upsert_artifact(self, args):
        src, sha, payload, size = args
        for a in self.db.artifacts:
            if a.source_file_id == src and a.content_sha256 == sha and a.derived_kind == "step_mesh":
                a.last_accessed_at += 1
                return
        self.db.artifacts.append(_DerivedArtifact(
            source_file_id=src,
            content_sha256=sha,
            derived_kind="step_mesh",
            payload=payload,
        ))


class _FakeDB:
    def __init__(self) -> None:
        self.jobs: List[_StepJob] = []
        self.files: List[_File] = []
        self.artifacts: List[_DerivedArtifact] = []
        self.listeners: Dict[str, List[Callable]] = {}
        self._counter = 0

    def add_file(self, *, storage_key: Optional[str], deleted: bool = False) -> _File:
        f = _File(id=uuid.uuid4(), storage_key=storage_key, deleted_at="x" if deleted else None)
        self.files.append(f)
        return f

    def enqueue_job(self, file_id: uuid.UUID, input_spec: Optional[Dict] = None) -> _StepJob:
        self._counter += 1
        j = _StepJob(id=uuid.uuid4(), file_id=file_id, input_spec=input_spec, created_at=self._counter)
        self.jobs.append(j)
        return j

    def file_by_id(self, fid: uuid.UUID) -> _File:
        return next(f for f in self.files if f.id == fid)


class _FakePool:
    def __init__(self, db: _FakeDB) -> None:
        self.db = db

    def acquire(self):
        pool = self

        class _Acq:
            async def __aenter__(self_inner):
                return _FakeConn(pool.db)

            async def __aexit__(self_inner, exc_type, exc, tb):
                return False

        return _Acq()

    async def execute(self, query: str, *args):
        conn = _FakeConn(self.db)
        return await conn.execute(query, *args)


# --------------------------------------------------------------------------- tests


CUBE_STEP = b"ISO-10303-21;\nHEADER;\nFILE_DESCRIPTION(('cube'),'2;1');\nDATA;\nENDSEC;\nEND-ISO-10303-21;\n"


def _make_worker(driver: _FakeDriver, db: _FakeDB, storage: _FakeStorage) -> AutoTessWorker:
    return AutoTessWorker(
        pool=_FakePool(db),
        storage_getter=lambda: storage,
        driver=driver,
        timeout=5,
    )


@pytest.mark.asyncio
async def test_no_queued_jobs_returns_false():
    db = _FakeDB()
    worker = _make_worker(_FakeDriver(), db, _FakeStorage())
    assert await worker.run_one() is False


@pytest.mark.asyncio
async def test_happy_path_tessellates_and_persists():
    db = _FakeDB()
    storage = _FakeStorage()
    f = db.add_file(storage_key="projects/p1/cube.step")
    storage.blobs[f.storage_key] = CUBE_STEP
    job = db.enqueue_job(f.id)

    glb_payload = b"\x00\x01GLBPAYLOAD\x02\x03" * 16
    driver = _FakeDriver(output=glb_payload)
    worker = _make_worker(driver, db, storage)

    assert await worker.run_one() is True

    # Job marked done with the right keys
    assert job.status == "done"
    assert job.error is None
    assert job.content_sha256 == hashlib.sha256(CUBE_STEP).hexdigest()
    assert job.mesh_storage_key == f"meshes/step/{job.content_sha256}.glb"

    # File row updated with mesh_storage_key
    assert db.file_by_id(f.id).mesh_storage_key == job.mesh_storage_key

    # Mesh blob in storage
    assert storage.blobs[job.mesh_storage_key] == glb_payload

    # derived_artifacts row created
    assert len(db.artifacts) == 1
    art = db.artifacts[0]
    assert art.source_file_id == f.id
    assert art.derived_kind == "step_mesh"
    assert art.content_sha256 == job.content_sha256
    assert art.payload == glb_payload

    # Driver invoked once with the right STEP bytes
    assert len(driver.calls) == 1
    assert driver.calls[0][0] == len(CUBE_STEP)


@pytest.mark.asyncio
async def test_idempotent_on_cache_hit():
    """Second job for same (file, sha256) reuses cached artifact, skips pyworker."""
    db = _FakeDB()
    storage = _FakeStorage()
    f = db.add_file(storage_key="projects/p1/cube.step")
    storage.blobs[f.storage_key] = CUBE_STEP

    sha = hashlib.sha256(CUBE_STEP).hexdigest()
    db.artifacts.append(_DerivedArtifact(
        source_file_id=f.id,
        content_sha256=sha,
        derived_kind="step_mesh",
        payload=b"cached-glb",
    ))
    job = db.enqueue_job(f.id)

    driver = _FakeDriver(output=b"SHOULD-NOT-BE-CALLED")
    worker = _make_worker(driver, db, storage)

    assert await worker.run_one() is True
    assert driver.calls == []  # pyworker not invoked on cache hit
    assert job.status == "done"
    assert job.mesh_storage_key == f"meshes/step/{sha}.glb"


@pytest.mark.asyncio
async def test_missing_storage_key_marks_error():
    db = _FakeDB()
    storage = _FakeStorage()
    f = db.add_file(storage_key=None)
    job = db.enqueue_job(f.id)

    worker = _make_worker(_FakeDriver(), db, storage)
    assert await worker.run_one() is True
    assert job.status == "error"
    assert "storage_key" in (job.error or "")


@pytest.mark.asyncio
async def test_storage_get_missing_blob_marks_error():
    db = _FakeDB()
    storage = _FakeStorage()
    f = db.add_file(storage_key="projects/p1/missing.step")
    job = db.enqueue_job(f.id)

    worker = _make_worker(_FakeDriver(), db, storage)
    assert await worker.run_one() is True
    assert job.status == "error"
    assert "storage missing" in (job.error or "")


@pytest.mark.asyncio
async def test_pyworker_failure_marks_error_does_not_crash():
    db = _FakeDB()
    storage = _FakeStorage()
    f = db.add_file(storage_key="projects/p1/cube.step")
    storage.blobs[f.storage_key] = CUBE_STEP
    job = db.enqueue_job(f.id)

    driver = _FakeDriver(raise_exc=RuntimeError("sidecar exit 1: pythonocc not installed"))
    worker = _make_worker(driver, db, storage)

    # Must not raise — soft fail by design.
    assert await worker.run_one() is True
    assert job.status == "error"
    assert "pythonocc" in (job.error or "").lower() or "sidecar" in (job.error or "").lower()


@pytest.mark.asyncio
async def test_pyworker_timeout_marks_error():
    db = _FakeDB()
    storage = _FakeStorage()
    f = db.add_file(storage_key="projects/p1/cube.step")
    storage.blobs[f.storage_key] = CUBE_STEP
    db.enqueue_job(f.id)

    driver = _FakeDriver(delay=10.0)
    worker = _make_worker(driver, db, storage)
    worker.timeout = 0  # force immediate timeout

    assert await worker.run_one() is True
    assert db.jobs[0].status == "error"
    assert "timeout" in (db.jobs[0].error or "").lower()


@pytest.mark.asyncio
async def test_empty_step_marks_error():
    db = _FakeDB()
    storage = _FakeStorage()
    f = db.add_file(storage_key="projects/p1/empty.step")
    storage.blobs[f.storage_key] = b""
    job = db.enqueue_job(f.id)

    worker = _make_worker(_FakeDriver(), db, storage)
    assert await worker.run_one() is True
    assert job.status == "error"


@pytest.mark.asyncio
async def test_skips_jobs_for_deleted_files():
    db = _FakeDB()
    storage = _FakeStorage()
    f = db.add_file(storage_key="projects/p1/cube.step", deleted=True)
    storage.blobs[f.storage_key] = CUBE_STEP
    db.enqueue_job(f.id)

    worker = _make_worker(_FakeDriver(), db, storage)
    assert await worker.run_one() is False  # claim filter skips deleted files


@pytest.mark.asyncio
async def test_input_spec_passed_through_to_driver():
    db = _FakeDB()
    storage = _FakeStorage()
    f = db.add_file(storage_key="projects/p1/cube.step")
    storage.blobs[f.storage_key] = CUBE_STEP
    db.enqueue_job(f.id, input_spec={"resolution": 12345, "export_format": "glb", "scale": 2.0})

    driver = _FakeDriver()
    worker = _make_worker(driver, db, storage)
    await worker.run_one()

    assert driver.calls[0][1]["resolution"] == 12345
    assert driver.calls[0][1]["scale"] == 2.0


@pytest.mark.asyncio
async def test_empty_glb_marks_error():
    db = _FakeDB()
    storage = _FakeStorage()
    f = db.add_file(storage_key="projects/p1/cube.step")
    storage.blobs[f.storage_key] = CUBE_STEP
    job = db.enqueue_job(f.id)

    worker = _make_worker(_FakeDriver(output=b""), db, storage)
    assert await worker.run_one() is True
    assert job.status == "error"
    assert "empty" in (job.error or "").lower()


# --------------------------------------------------------------------------- helper unit


@pytest.mark.asyncio
async def test_read_storage_unpacks_tuple_handle():
    """Regression: storage.get returns (reader, content_type) tuple."""
    storage = _FakeStorage()
    storage.blobs["k"] = b"payload"
    data = await _read_storage(storage, "k")
    assert data == b"payload"
