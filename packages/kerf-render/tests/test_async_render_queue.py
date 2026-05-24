"""Tests: async /run-render job-queue path and CyclesQueueWorker registration.

Covers:
 1. POST /run-render with a wired DB pool → enqueues a render_jobs row and
    returns {job_id, status: "queued"} without invoking Blender.
 2. GET /render/status/{job_id} → reads the render_jobs row.
 3. CyclesQueueWorker is registered in _build_workers when kerf_render is
    available (i.e., it is in sys.path for this test run).
 4. GPU env-flag gate: _build_render_script includes/excludes the CUDA block.
 5. ComputeBackend interface: LocalSubprocessBackend submit + poll round-trip.
"""
from __future__ import annotations

import asyncio
import json
import os
import uuid

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Fake asyncpg pool for render_jobs
# ---------------------------------------------------------------------------


class FakeRenderPool:
    """In-memory asyncpg pool stub that handles render_jobs SQL."""

    def __init__(self):
        self.rows: dict = {}

    async def execute(self, sql, *args):
        q = " ".join(sql.split())
        if "INSERT INTO render_jobs" in q:
            # args: job_id, scene_blob_hash, preset, samples_total, payload_json
            job_id, blob_hash, preset, samples_total, payload_json = args
            self.rows[str(job_id)] = {
                "id": str(job_id),
                "user_id": None,
                "scene_blob_hash": blob_hash,
                "preset": preset,
                "status": "queued",
                "samples_done": 0,
                "samples_total": samples_total,
                "payload_json": payload_json,
                "signed_url": None,
                "error": None,
                "created_at": "t0",
                "updated_at": "t0",
            }
            return "INSERT 0 1"
        if "SET status = 'cancelled'" in q:
            jid = args[0]
            row = self.rows.get(jid)
            if row and row["status"] not in ("complete", "failed", "cancelled"):
                row["status"] = "cancelled"
                return "UPDATE 1"
            return "UPDATE 0"
        # Catch-all for other updates (mark_rendering, update_progress, etc.)
        return "UPDATE 1"

    async def fetchrow(self, sql, *args):
        q = " ".join(sql.split())
        if "FROM render_jobs" in q and "WHERE id = $1" in q:
            return self.rows.get(str(args[0]))
        return None


# ---------------------------------------------------------------------------
# Fake FastAPI Request with state.pool
# ---------------------------------------------------------------------------


class FakeState:
    def __init__(self, pool):
        self.pool = pool


class FakeApp:
    def __init__(self, pool):
        self.state = FakeState(pool)


class FakeRequest:
    def __init__(self, pool=None):
        self.app = FakeApp(pool)


# ---------------------------------------------------------------------------
# 1. POST /run-render enqueues a job when pool is present
# ---------------------------------------------------------------------------


def test_run_render_enqueues_job():
    from kerf_render.routes import run_render, RenderRequest

    pool = FakeRenderPool()
    req = RenderRequest(
        scene_file_id="f1",
        mesh_b64="",
        render_settings={"samples": 256},
    )
    fake_request = FakeRequest(pool=pool)

    result = run(run_render(req, fake_request))

    assert result["status"] == "queued", result
    job_id = result["job_id"]
    assert job_id in pool.rows
    assert pool.rows[job_id]["status"] == "queued"


def test_run_render_returns_job_id():
    from kerf_render.routes import run_render, RenderRequest

    pool = FakeRenderPool()
    req = RenderRequest(scene_file_id="f2", mesh_b64="")
    fake_request = FakeRequest(pool=pool)

    result = run(run_render(req, fake_request))
    assert "job_id" in result
    # job_id should be a valid UUID
    uuid.UUID(result["job_id"])  # raises if invalid


def test_run_render_stores_payload_json():
    """The payload_json column stores enough info for the queue worker."""
    from kerf_render.routes import run_render, RenderRequest

    pool = FakeRenderPool()
    req = RenderRequest(
        scene_file_id="f3",
        mesh_b64="",
        render_settings={"samples": 1024, "output_format": "png"},
    )
    fake_request = FakeRequest(pool=pool)
    result = run(run_render(req, fake_request))
    row = pool.rows[result["job_id"]]
    payload = json.loads(row["payload_json"])
    assert "scene_file_id" in payload
    assert payload["scene_file_id"] == "f3"


# ---------------------------------------------------------------------------
# 2. GET /render/status/{job_id}
# ---------------------------------------------------------------------------


def test_get_render_status_queued():
    from kerf_render.routes import get_render_status, run_render, RenderRequest

    pool = FakeRenderPool()
    req = RenderRequest(scene_file_id="f4", mesh_b64="")
    fake_request = FakeRequest(pool=pool)
    enqueue = run(run_render(req, fake_request))
    job_id = enqueue["job_id"]

    status = run(get_render_status(job_id, fake_request))
    assert status["status"] == "queued"
    assert status["job_id"] == job_id


def test_get_render_status_not_found():
    from kerf_render.routes import get_render_status

    pool = FakeRenderPool()
    fake_request = FakeRequest(pool=pool)
    result = run(get_render_status("no-such-id", fake_request))
    assert result["error"] == "not_found"


def test_get_render_status_no_pool():
    from kerf_render.routes import get_render_status

    fake_request = FakeRequest(pool=None)
    result = run(get_render_status("any-id", fake_request))
    assert result["error"] == "no_pool"


# ---------------------------------------------------------------------------
# 3. CyclesQueueWorker is registered in _build_workers
# ---------------------------------------------------------------------------


def test_cycles_queue_worker_registered_in_build_workers():
    """_build_workers must include at least one CyclesQueueWorker."""
    from kerf_workers.runner import _build_workers
    from kerf_render.queue_worker import CyclesQueueWorker

    pool = FakeRenderPool()
    workers = _build_workers(
        pool,
        storage_getter=lambda: None,
        fem_count=0,
        sim_count=0,
        tess_count=0,
        cam_count=0,
        cycles_count=1,
        compaction_count=0,
    )

    cycles_workers = [w for w in workers if isinstance(w, CyclesQueueWorker)]
    assert len(cycles_workers) == 1, (
        f"Expected 1 CyclesQueueWorker, got {len(cycles_workers)}. "
        f"All workers: {[type(w).__name__ for w in workers]}"
    )


def test_cycles_worker_count_zero_skipped():
    """cycles_count=0 must produce no CyclesQueueWorker."""
    from kerf_workers.runner import _build_workers
    from kerf_render.queue_worker import CyclesQueueWorker

    pool = FakeRenderPool()
    workers = _build_workers(
        pool,
        storage_getter=lambda: None,
        fem_count=0, sim_count=0, tess_count=0,
        cam_count=0, cycles_count=0, compaction_count=0,
    )
    assert not any(isinstance(w, CyclesQueueWorker) for w in workers)


# ---------------------------------------------------------------------------
# 4. GPU env-flag gate in _build_render_script
# ---------------------------------------------------------------------------


def test_build_render_script_no_gpu_by_default(tmp_path, monkeypatch):
    """Without KERF_RENDER_GPU set, the script must NOT contain CUDA lines."""
    from kerf_render.cycles_worker import _build_render_script

    monkeypatch.delenv("KERF_RENDER_GPU", raising=False)
    script = _build_render_script(
        gltf_path=str(tmp_path / "scene.glb"),
        script_str="def main(): pass\n",
        output_path=str(tmp_path / "render.png"),
        output_format="png",
        samples=256,
        resolution=(1920, 1080),
        gpu_enabled=False,
    )
    assert "CUDA" not in script
    assert "compute_device_type" not in script


def test_build_render_script_gpu_enabled(tmp_path):
    """With gpu_enabled=True, the script must contain the CUDA activation block."""
    from kerf_render.cycles_worker import _build_render_script

    script = _build_render_script(
        gltf_path=str(tmp_path / "scene.glb"),
        script_str="def main(): pass\n",
        output_path=str(tmp_path / "render.png"),
        output_format="png",
        samples=256,
        resolution=(1920, 1080),
        gpu_enabled=True,
    )
    assert "CUDA" in script
    assert "compute_device_type" in script
    assert 'cycles.device = "GPU"' in script


def test_invoke_blender_reads_gpu_env(tmp_path, monkeypatch):
    """CyclesWorker._invoke_blender passes gpu_enabled from KERF_RENDER_GPU."""
    from kerf_render.cycles_worker import CyclesWorker, CyclesWorkerConfig, _build_render_script

    captured = {}

    def fake_build_render_script(**kwargs):
        captured["gpu_enabled"] = kwargs.get("gpu_enabled", False)
        return "def main(): pass\n"

    monkeypatch.setattr("kerf_render.cycles_worker._build_render_script", fake_build_render_script)
    monkeypatch.setenv("KERF_RENDER_GPU", "1")

    # Also stub _run_blender so we don't actually invoke blender.
    monkeypatch.setattr(
        "kerf_render.cycles_worker._run_blender",
        lambda *a, **kw: (0, "", ""),
    )

    cfg = CyclesWorkerConfig(cache_dir=str(tmp_path / "cache"))
    worker = CyclesWorker(cfg)

    # _invoke_blender will fail because there's no output file, but the
    # important thing is that fake_build_render_script was called with
    # gpu_enabled=True.
    worker._invoke_blender(
        gltf_bytes=b"",
        script_str="def main(): pass\n",
        output_format="png",
        samples=256,
        resolution=(1920, 1080),
        timeout=30,
        progress_callback=None,
    )

    assert captured.get("gpu_enabled") is True


# ---------------------------------------------------------------------------
# 5. ComputeBackend / LocalSubprocessBackend interface
# ---------------------------------------------------------------------------


def test_compute_backend_is_abstract():
    from kerf_workers.compute_backend import ComputeBackend
    import inspect

    assert inspect.isabstract(ComputeBackend)


def test_local_subprocess_backend_submit_render():
    from kerf_workers.compute_backend import LocalSubprocessBackend

    pool = FakeRenderPool()
    backend = LocalSubprocessBackend(pool)

    job_id = run(backend.submit("render", {
        "user_id": "u1",
        "scene_blob_hash": "abc123",
        "preset": "draft",
        "output_format": "png",
    }))

    assert isinstance(job_id, str)
    assert job_id in pool.rows
    assert pool.rows[job_id]["status"] == "queued"


def test_local_subprocess_backend_poll():
    from kerf_workers.compute_backend import LocalSubprocessBackend

    pool = FakeRenderPool()
    backend = LocalSubprocessBackend(pool)

    job_id = run(backend.submit("render", {
        "user_id": "u1",
        "scene_blob_hash": "h2",
        "preset": "standard",
    }))

    status = run(backend.poll(job_id))
    assert status["status"] == "queued"
    assert status["result"] is None
    assert status["error"] is None


def test_local_subprocess_backend_poll_not_found():
    from kerf_workers.compute_backend import LocalSubprocessBackend

    pool = FakeRenderPool()
    backend = LocalSubprocessBackend(pool)

    status = run(backend.poll("ghost-id"))
    assert status["status"] == "not_found"


def test_local_subprocess_backend_unsupported_job_type():
    from kerf_workers.compute_backend import LocalSubprocessBackend

    pool = FakeRenderPool()
    backend = LocalSubprocessBackend(pool)

    with pytest.raises(NotImplementedError):
        run(backend.submit("unknown_type", {}))
