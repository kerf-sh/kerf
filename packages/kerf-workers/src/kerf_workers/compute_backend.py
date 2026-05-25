"""kerf-workers: ComputeBackend open-core abstraction.

Defines the MIT-licensed interface for submitting and polling compute jobs
(renders, simulations, etc.) against an arbitrary backend.

Concrete implementations
------------------------
:class:`LocalSubprocessBackend`
    Ships in this package (MIT).  Wraps the local worker poll loop: jobs
    are inserted into Postgres and drained by whichever :class:`BaseWorker`
    subclass handles that ``job_type``.

Future proprietary extension point (DO NOT implement here)
----------------------------------------------------------
A ``KoyebGPUBackend`` that provisions on-demand Koyeb GPU instances for
rendering belongs in the **proprietary cloud/ tree**, NOT in this module.
It should subclass :class:`ComputeBackend` and live at::

    cloud/kerf_cloud/compute/koyeb_gpu_backend.py

The interface contract is intentionally minimal so the swap is transparent to
callers.  Typical usage::

    # MIT path (local / self-hosted):
    backend = LocalSubprocessBackend(pool=pool)

    # Proprietary path (cloud/):
    # from kerf_cloud.compute.koyeb_gpu_backend import KoyebGPUBackend
    # backend = KoyebGPUBackend(koyeb_api_token=..., region=...)

    job_id = await backend.submit("render", payload)
    status = await backend.poll(job_id)

Open-core seam: nothing in this file may import the ``cloud`` package or any
proprietary module.  The ``KoyebGPUBackend`` integration point is documented
here only as a docstring — no import, no reference at runtime.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class ComputeBackend(ABC):
    """Abstract compute backend: submit a job, poll for its status/result.

    All methods are ``async`` so implementations can use asyncpg, aiohttp,
    or the Koyeb GPU-provider API without blocking the event loop.
    """

    @abstractmethod
    async def submit(self, job_type: str, payload: Dict[str, Any]) -> str:
        """Enqueue a compute job and return its opaque job ID.

        Parameters
        ----------
        job_type:
            A string tag identifying the kind of work, e.g. ``"render"``,
            ``"fem"``, ``"spice"``.  Backends use this to route the payload
            to the correct worker or machine type.
        payload:
            A JSON-serialisable dict containing all inputs required to execute
            the job.  The schema is agreed between the caller and the concrete
            backend / worker.

        Returns
        -------
        str
            An opaque job identifier.  Pass it back to :meth:`poll` to check
            progress or retrieve the result.
        """

    @abstractmethod
    async def poll(self, job_id: str) -> Dict[str, Any]:
        """Return the current status and (when complete) result of a job.

        Parameters
        ----------
        job_id:
            The identifier returned by :meth:`submit`.

        Returns
        -------
        dict
            Always contains at least:

            ``status`` (``str``)
                One of ``"queued"``, ``"running"``, ``"complete"``,
                ``"failed"``, ``"cancelled"``.
            ``result`` (``dict | None``)
                Present when ``status == "complete"``; ``None`` otherwise.
            ``error`` (``str | None``)
                Present when ``status == "failed"``; ``None`` otherwise.
        """


# ---------------------------------------------------------------------------
# LocalSubprocessBackend — MIT, ships in this package
# ---------------------------------------------------------------------------


class LocalSubprocessBackend(ComputeBackend):
    """Concrete backend that delegates to the local Postgres job-queue harness.

    Jobs are inserted into the appropriate Postgres table (e.g.
    ``render_jobs``) and drained by the :class:`~kerf_workers.base.BaseWorker`
    subclass registered for that ``job_type`` in
    :func:`~kerf_workers.runner._build_workers`.

    This backend is suitable for:
    - Local / self-hosted deployments.
    - Development and CI environments.
    - Cloud deployments where workers run as separate processes on the same DB.

    Extension point
    ~~~~~~~~~~~~~~~
    For GPU rendering on Koyeb (on-demand, scale-to-zero GPU instances),
    replace this backend with a ``KoyebGPUBackend`` from the proprietary
    ``cloud/`` tree. The swap is transparent to callers because both
    implement :class:`ComputeBackend`.

    Parameters
    ----------
    pool:
        An ``asyncpg.Pool`` connected to the Kerf Postgres database.
    """

    def __init__(self, pool) -> None:
        self._pool = pool

    async def submit(self, job_type: str, payload: Dict[str, Any]) -> str:
        """Insert a job row and return the generated job ID.

        Currently supports ``job_type="render"`` (delegates to
        :func:`kerf_render.job_lifecycle.submit_job`).  Add branches here as
        new job types are integrated.
        """
        if job_type == "render":
            from kerf_render.job_lifecycle import submit_job  # lazy: MIT only
            user_id = payload.get("user_id", "anonymous")
            scene_blob_hash = payload.get("scene_blob_hash", str(uuid.uuid4()))
            preset = payload.get("preset", "standard")
            output_format = payload.get("output_format", "png")
            job_id = payload.get("job_id") or str(uuid.uuid4())
            return await submit_job(
                self._pool,
                user_id=user_id,
                scene_blob_hash=scene_blob_hash,
                preset=preset,
                output_format=output_format,
                job_id=job_id,
            )

        raise NotImplementedError(
            f"LocalSubprocessBackend: unsupported job_type={job_type!r}. "
            "Add a branch in submit() or register a dedicated worker."
        )

    async def poll(self, job_id: str) -> Dict[str, Any]:
        """Fetch the current row from ``render_jobs`` and normalise it.

        Only ``render`` jobs are stored in ``render_jobs``; extend this method
        for other tables when additional job types are integrated.
        """
        from kerf_render.job_lifecycle import get_job_status  # lazy: MIT only
        row = await get_job_status(self._pool, job_id)
        if row is None:
            return {"status": "not_found", "result": None, "error": None}

        status = row["status"]  # queued | rendering | complete | failed | cancelled
        # Normalise "rendering" → "running" to match the generic interface.
        if status == "rendering":
            status = "running"
        elif status == "complete":
            status = "complete"

        result: Optional[Dict[str, Any]] = None
        if row["status"] == "complete" and row.get("signed_url"):
            result = {"signed_url": row["signed_url"]}

        return {
            "status": status,
            "result": result,
            "error": row.get("error"),
            # Pass-through progress fields useful for polling UIs.
            "samples_done": row.get("samples_done", 0),
            "samples_total": row.get("samples_total", 0),
        }


__all__ = ["ComputeBackend", "LocalSubprocessBackend"]
