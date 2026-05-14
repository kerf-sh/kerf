"""
Compatibility shims for running kerf_fem outside of the legacy backend.

When kerf_fem is installed as a plugin (and `tools.registry` / `workers.base`
are not on the path) these thin replacements are used so the module still
imports cleanly.  The real implementations are provided by kerf-core at
runtime — these shims are only needed during unit-testing or standalone import.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable


# ---------------------------------------------------------------------------
# ToolSpec / registry shims
# ---------------------------------------------------------------------------

@dataclass
class ToolSpec:
    name: str
    description: str
    input_schema: dict


_registry: list = []


def register(spec: "ToolSpec", write: bool = False):
    def decorator(fn: Callable) -> Callable:
        _registry.append({"spec": spec, "write": write, "fn": fn})
        return fn
    return decorator


def ok_payload(v: Any) -> str:
    return json.dumps(v)


def err_payload(msg: str, code: str) -> str:
    return json.dumps({"error": msg, "code": code})


# ---------------------------------------------------------------------------
# ProjectCtx shim
# ---------------------------------------------------------------------------

class ProjectCtx:
    """Minimal stand-in for backend.tools.context.ProjectCtx used in tests."""
    def __init__(self, pool=None, project_id=None, user_id=None, storage=None,
                 http_client=None, file_revisions_max: int = 200):
        self.pool = pool
        self.project_id = project_id
        self.user_id = user_id
        self.storage = storage
        self.http_client = http_client
        self.file_revisions_max = file_revisions_max


# ---------------------------------------------------------------------------
# BaseWorker shim
# ---------------------------------------------------------------------------

import asyncio
import logging
from abc import ABC, abstractmethod

_logger = logging.getLogger(__name__)


class BaseWorker(ABC):
    def __init__(self, name: str, pool, poll_interval: float = 5.0,
                 error_delay: float = 2.0):
        self.name = name
        self.pool = pool
        self.poll_interval = poll_interval
        self.error_delay = error_delay
        self._shutdown = False

    def stop(self):
        self._shutdown = True

    async def run(self, ctx: asyncio.TaskGroup):
        task = ctx.create_task(self._loop())
        try:
            await task
        except asyncio.CancelledError:
            self._shutdown = True

    async def _loop(self):
        while not self._shutdown:
            try:
                ran = await self.run_one()
                if not ran:
                    await asyncio.sleep(self.poll_interval)
            except asyncio.CancelledError:
                break
            except Exception:
                _logger.exception(f"{self.name}: run_one error")
                await asyncio.sleep(self.error_delay)

    @abstractmethod
    async def run_one(self) -> bool:
        pass

    async def claim_job(self, tx, table: str, file_ref_table: str,
                        status_col: str = "status"):
        row = await tx.fetchrow(
            f"""
            SELECT j.id, j.file_id, f.project_id, f.storage_key, j.input_spec
            FROM {table} j
            JOIN {file_ref_table} f ON f.id = j.file_id
            WHERE j.{status_col} = 'queued' AND f.deleted_at IS NULL
            ORDER BY j.created_at ASC
            FOR UPDATE OF j SKIP LOCKED
            LIMIT 1
            """
        )
        if row is None:
            return None
        job_id = row["id"]
        if not row["storage_key"]:
            await tx.execute(
                f"UPDATE {table} SET status='error', error='file has no storage_key', "
                f"finished_at=now() WHERE id = $1",
                job_id,
            )
            return None
        await tx.execute(
            f"UPDATE {table} SET status='running', started_at=now() WHERE id = $1",
            job_id,
        )
        return row

    async def mark_error(self, table: str, job_id, error: str):
        try:
            await self.pool.execute(
                f"UPDATE {table} SET status='error', error=$2, finished_at=now() WHERE id=$1",
                job_id, error[:800],
            )
        except Exception:
            _logger.exception(f"{self.name}: mark_error failed (job={job_id})")

    async def mark_done(self, table: str, job_id, result_json: dict):
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    f"UPDATE {table} SET status='done', result_json=$2, finished_at=now(), "
                    f"error=null WHERE id=$1",
                    job_id, result_json,
                )
