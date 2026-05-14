"""
AutoTessWorker — cloud-tier STEP pre-tessellation worker.

Wakes on PG NOTIFY ``step_file_uploaded`` (payload = file_id) and processes
``step_tessellation_jobs`` rows where ``status='queued'``. Pulls the STEP blob
from object storage, hands it to the pyworker ``/run-tess`` route (occt-import-js
Node sidecar), and stores the resulting GLB in ``derived_artifacts`` keyed by
``(file_id, content_sha256, 'step_mesh')`` for content-hash idempotency. The
file row's ``mesh_storage_key`` is populated so the frontend can resolve the
mesh without going through the artifact table.

This worker is **cloud-tier-only**. It must not be started when
``settings.local_mode`` is True or ``settings.cloud_enabled`` is False — the
OSS local-install path tessellates in the browser. Gating happens at the
``start_all_workers`` call site in ``main.py``; this module assumes the
caller already decided to start it.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from typing import Callable, Optional

import asyncpg

from kerf_tess.base import BaseWorker
from kerf_tess.specs import TessInputSpec


logger = logging.getLogger(__name__)


_STUCK_RUNNING_RECOVERY_SECONDS = 600
_NOTIFY_CHANNEL = "step_file_uploaded"


async def notify_step_uploaded(conn: asyncpg.Connection, file_id: str) -> None:
    """Fire PG NOTIFY on ``step_file_uploaded`` so the worker wakes immediately."""
    await conn.execute("SELECT pg_notify($1, $2)", _NOTIFY_CHANNEL, file_id)


class _TessHTTPDriver:
    """Calls pyworker /run-tess and returns the raw GLB bytes."""

    def __init__(self, pyworker_url: str, timeout: int) -> None:
        self.pyworker_url = pyworker_url
        self.timeout = timeout

    async def tessellate(self, step_bytes: bytes, spec: TessInputSpec) -> bytes:
        import base64
        import aiohttp

        req = {
            "step_b64": base64.b64encode(step_bytes).decode(),
            "input_spec": spec.to_dict(),
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.pyworker_url}/run-tess",
                json=req,
                timeout=aiohttp.ClientTimeout(total=self.timeout + 30),
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    raise RuntimeError(f"pyworker status {resp.status}: {body[:400]}")
                data = await resp.json()

        errors = data.get("errors") or []
        if errors:
            raise RuntimeError(f"pyworker tess errors: {errors}")

        glb_b64 = data.get("glb_b64") or ""
        if not glb_b64:
            raise RuntimeError("pyworker returned empty glb_b64")

        return base64.b64decode(glb_b64)


class AutoTessWorker(BaseWorker):
    """Cloud-tier STEP → GLB pre-tessellation worker driven by PG LISTEN/NOTIFY."""

    name = "auto_tess"

    def __init__(
        self,
        pool: asyncpg.Pool,
        storage_getter: Callable,
        pyworker_url: str = "http://localhost:8090",
        poll_interval: float = 60.0,
        timeout: int = 300,
        driver: Optional[_TessHTTPDriver] = None,
    ) -> None:
        super().__init__(self.name, pool, poll_interval)
        self.storage_getter = storage_getter
        self.driver = driver if driver is not None else _TessHTTPDriver(
            pyworker_url=pyworker_url, timeout=timeout
        )
        self.timeout = timeout
        self._wake = asyncio.Event()
        self._listener_task: Optional[asyncio.Task] = None

    # ------------------------------------------------------------------ run loop

    async def run(self, ctx: asyncio.TaskGroup) -> None:
        self._listener_task = ctx.create_task(self._listen_loop())
        try:
            await super().run(ctx)
        finally:
            if self._listener_task and not self._listener_task.done():
                self._listener_task.cancel()

    async def _loop(self) -> None:
        # Override the polling loop: drain whatever's queued, then sleep until
        # either a NOTIFY arrives or the long fallback poll fires. The fallback
        # exists because NOTIFY is best-effort across reconnects and we don't
        # want a missed signal to strand a job forever.
        while not self._shutdown:
            try:
                await self._recover_stuck_jobs()
                drained = False
                while not self._shutdown:
                    ran = await self.run_one()
                    if not ran:
                        break
                    drained = True
                if drained:
                    continue
                try:
                    await asyncio.wait_for(self._wake.wait(), timeout=self.poll_interval)
                except asyncio.TimeoutError:
                    pass
                self._wake.clear()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("auto_tess: run loop error, backing off")
                await asyncio.sleep(self.error_delay)

    # ----------------------------------------------------------------- listener

    async def _listen_loop(self) -> None:
        def _on_notify(*_args):
            self._wake.set()

        while not self._shutdown:
            try:
                async with self.pool.acquire() as conn:
                    await conn.add_listener(_NOTIFY_CHANNEL, _on_notify)
                    try:
                        while not self._shutdown:
                            # Keep the connection checked-out so the LISTEN
                            # stays active; asyncpg fires callbacks on this
                            # connection's read path. Sleep in long chunks
                            # rather than busy-wait.
                            await asyncio.sleep(3600)
                    finally:
                        try:
                            await conn.remove_listener(_NOTIFY_CHANNEL, _on_notify)
                        except Exception:
                            pass
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("auto_tess: listener error, reconnecting in 5s")
                await asyncio.sleep(5.0)

    # ------------------------------------------------------------- recovery

    async def _recover_stuck_jobs(self) -> None:
        try:
            await self.pool.execute(
                f"""
                UPDATE step_tessellation_jobs
                SET status = 'queued', started_at = NULL
                WHERE status = 'running'
                  AND started_at IS NOT NULL
                  AND started_at < now() - interval '{int(_STUCK_RUNNING_RECOVERY_SECONDS)} seconds'
                """,
            )
        except Exception:
            logger.exception("auto_tess: stuck-job recovery failed")

    # ------------------------------------------------------------- core work

    async def run_one(self) -> bool:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """
                    SELECT j.id, j.file_id, f.project_id, f.storage_key, j.input_spec
                    FROM step_tessellation_jobs j
                    JOIN files f ON f.id = j.file_id
                    WHERE j.status = 'queued'
                      AND f.deleted_at IS NULL
                    ORDER BY j.created_at ASC
                    FOR UPDATE OF j SKIP LOCKED
                    LIMIT 1
                    """
                )
                if row is None:
                    return False

                job_id = row["id"]
                file_id = row["file_id"]
                storage_key: Optional[str] = row["storage_key"]
                input_spec_raw = row["input_spec"]

                if not storage_key:
                    await conn.execute(
                        """
                        UPDATE step_tessellation_jobs
                        SET status='error', error='file has no storage_key',
                            finished_at=now()
                        WHERE id = $1
                        """,
                        job_id,
                    )
                    return True

                await conn.execute(
                    """
                    UPDATE step_tessellation_jobs
                    SET status='running', started_at=now(), error=NULL
                    WHERE id = $1
                    """,
                    job_id,
                )

        spec = TessInputSpec.from_dict(
            input_spec_raw if isinstance(input_spec_raw, dict)
            else (json.loads(input_spec_raw) if input_spec_raw else {})
        )

        t0 = time.monotonic()
        await self._process(job_id=job_id, file_id=file_id, storage_key=storage_key, spec=spec, t0=t0)
        return True

    async def _process(
        self,
        *,
        job_id,
        file_id,
        storage_key: str,
        spec: TessInputSpec,
        t0: float,
    ) -> None:
        storage = self.storage_getter()
        try:
            step_bytes = await _read_storage(storage, storage_key)
        except FileNotFoundError as e:
            await self._fail(job_id, file_id, f"storage missing: {e}", t0)
            return
        except Exception as e:
            logger.exception("auto_tess: download step failed (job=%s)", job_id)
            await self._fail(job_id, file_id, f"download step: {e}", t0)
            return

        if not step_bytes:
            await self._fail(job_id, file_id, "empty step file", t0)
            return

        sha256_hex = hashlib.sha256(step_bytes).hexdigest()

        cached = await self._reuse_cached_artifact(file_id, sha256_hex)
        if cached:
            await self._mark_done(
                job_id=job_id,
                file_id=file_id,
                content_sha256=sha256_hex,
                mesh_storage_key=cached,
            )
            duration_ms = int((time.monotonic() - t0) * 1000)
            logger.info(
                "auto_tess job_id=%s file_id=%s status=done cached=1 "
                "sha256=%s mesh_key=%s duration_ms=%d",
                job_id, file_id, sha256_hex[:12], cached, duration_ms,
            )
            return

        try:
            async with asyncio.timeout(self.timeout):
                glb_bytes = await self.driver.tessellate(step_bytes, spec)
        except asyncio.TimeoutError:
            await self._fail(job_id, file_id, "tessellation timeout", t0)
            return
        except Exception as e:
            logger.exception("auto_tess: tess failed (job=%s)", job_id)
            await self._fail(job_id, file_id, str(e), t0)
            return

        if not glb_bytes:
            await self._fail(job_id, file_id, "tessellator produced empty mesh", t0)
            return

        mesh_key = f"meshes/step/{sha256_hex}.glb"
        try:
            await _write_storage(storage, mesh_key, glb_bytes)
        except Exception as e:
            logger.exception("auto_tess: mesh put failed (job=%s)", job_id)
            await self._fail(job_id, file_id, f"mesh put: {e}", t0)
            return

        try:
            await self._persist_artifact(
                file_id=file_id,
                content_sha256=sha256_hex,
                payload=glb_bytes,
            )
        except Exception:
            # Artifact cache miss isn't fatal — the mesh is in storage and the
            # job row will still link the file via mesh_storage_key. Log loud.
            logger.exception("auto_tess: derived_artifact upsert failed (job=%s)", job_id)

        await self._mark_done(
            job_id=job_id,
            file_id=file_id,
            content_sha256=sha256_hex,
            mesh_storage_key=mesh_key,
        )

        duration_ms = int((time.monotonic() - t0) * 1000)
        logger.info(
            "auto_tess job_id=%s file_id=%s status=done cached=0 "
            "sha256=%s mesh_key=%s mesh_size=%d duration_ms=%d",
            job_id, file_id, sha256_hex[:12], mesh_key, len(glb_bytes), duration_ms,
        )

    # ----------------------------------------------------------- db helpers

    async def _reuse_cached_artifact(self, file_id, content_sha256: str) -> Optional[str]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id FROM derived_artifacts
                WHERE source_file_id = $1
                  AND content_sha256 = $2
                  AND derived_kind = 'step_mesh'
                """,
                file_id,
                content_sha256,
            )
            if not row:
                return None
            await conn.execute(
                "UPDATE derived_artifacts SET last_accessed_at = now() WHERE id = $1",
                row["id"],
            )
        return f"meshes/step/{content_sha256}.glb"

    async def _persist_artifact(self, *, file_id, content_sha256: str, payload: bytes) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO derived_artifacts
                    (source_file_id, content_sha256, derived_kind, payload, payload_size_bytes)
                VALUES ($1, $2, 'step_mesh', $3, $4)
                ON CONFLICT (source_file_id, content_sha256, derived_kind)
                DO UPDATE SET last_accessed_at = now()
                """,
                file_id,
                content_sha256,
                payload,
                len(payload),
            )

    async def _mark_done(
        self,
        *,
        job_id,
        file_id,
        content_sha256: str,
        mesh_storage_key: str,
    ) -> None:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    UPDATE step_tessellation_jobs
                    SET status='done', mesh_storage_key=$2, content_sha256=$3,
                        finished_at=now(), error=NULL
                    WHERE id = $1
                    """,
                    job_id,
                    mesh_storage_key,
                    content_sha256,
                )
                await conn.execute(
                    "UPDATE files SET mesh_storage_key = $2 WHERE id = $1",
                    file_id,
                    mesh_storage_key,
                )

    async def _fail(self, job_id, file_id, error: str, t0: float) -> None:
        truncated = error[:800] if len(error) > 800 else error
        try:
            await self.pool.execute(
                """
                UPDATE step_tessellation_jobs
                SET status='error', error=$2, finished_at=now()
                WHERE id = $1
                """,
                job_id,
                truncated,
            )
        except Exception:
            logger.exception("auto_tess: failed to mark error (job=%s)", job_id)
        duration_ms = int((time.monotonic() - t0) * 1000)
        logger.warning(
            "auto_tess job_id=%s file_id=%s status=error duration_ms=%d error=%s",
            job_id, file_id, duration_ms, truncated,
        )


# -------------------------------------------------------------- storage helpers


async def _read_storage(storage, key: str) -> bytes:
    """Read all bytes from a Storage backend.

    Storage.get returns ``(reader, content_type)`` with a sync file-like reader.
    """
    handle = await storage.get(key)
    if isinstance(handle, tuple):
        reader = handle[0]
    else:
        reader = handle
    try:
        data = reader.read()
        if asyncio.iscoroutine(data):
            data = await data
        return data
    finally:
        close = getattr(reader, "close", None)
        if callable(close):
            try:
                close()
            except Exception:
                pass


async def _write_storage(storage, key: str, payload: bytes) -> None:
    import io
    await storage.put(key, io.BytesIO(payload), "model/gltf-binary", len(payload))
