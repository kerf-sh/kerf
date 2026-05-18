"""Verification suite for kerf_render.job_lifecycle (T-106b).

Uses an in-memory fake asyncpg pool that understands just the SQL the
module issues, so the queued → rendering → complete/failed/cancelled
state machine is exercised without a database.

Follows the kerf-render test convention: a synchronous ``run(coro)``
helper drives the async API (this package's pytest config does not
enable asyncio auto-mode).
"""
from __future__ import annotations

import asyncio
import pathlib

from kerf_render.cycles_worker import PRESET_SAMPLES
from kerf_render.job_lifecycle import (
    cancel_job,
    get_job_status,
    mark_complete,
    mark_failed,
    mark_rendering,
    submit_job,
    update_progress,
)

_TERMINAL = {"complete", "failed", "cancelled"}


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class FakePool:
    """Minimal asyncpg-pool stand-in keyed on the SQL the module sends."""

    def __init__(self):
        self.rows = {}  # job_id -> row dict

    async def execute(self, sql, *args):
        q = " ".join(sql.split())
        if "INSERT INTO render_jobs" in q:
            jid, user_id, blob, preset, samples_total = args
            self.rows[jid] = {
                "id": jid, "user_id": user_id, "scene_blob_hash": blob,
                "preset": preset, "status": "queued", "samples_done": 0,
                "samples_total": samples_total, "signed_url": None,
                "error": None, "created_at": "t0", "updated_at": "t0",
            }
            return "INSERT 0 1"
        if "SET status = 'cancelled'" in q:
            jid = args[0]
            row = self.rows.get(jid)
            if row and row["status"] not in _TERMINAL:
                row["status"] = "cancelled"
                row["error"] = None
                return "UPDATE 1"
            return "UPDATE 0"
        if "SET status = 'rendering'" in q:
            jid, samples_total = args
            self.rows[jid].update(status="rendering", samples_total=samples_total)
            return "UPDATE 1"
        if "SET samples_done = $2, updated_at = now()" in q:
            jid, done = args
            self.rows[jid]["samples_done"] = done
            return "UPDATE 1"
        if "SET status = 'complete'" in q:
            jid, url = args
            r = self.rows[jid]
            r.update(status="complete", signed_url=url,
                     samples_done=r["samples_total"], error=None)
            return "UPDATE 1"
        if "SET status = 'failed'" in q:
            jid, err = args
            self.rows[jid].update(status="failed", error=err)
            return "UPDATE 1"
        raise AssertionError(f"unexpected execute: {q}")

    async def fetchrow(self, sql, *args):
        q = " ".join(sql.split())
        if "FROM render_jobs" in q and "WHERE id = $1" in q:
            return self.rows.get(args[0])
        raise AssertionError(f"unexpected fetchrow: {q}")


# ---------------------------------------------------------------------------
# Migration sanity
# ---------------------------------------------------------------------------


def test_migration_render_jobs_present_and_idempotent():
    """render_jobs lives in the consolidated baseline 0010_github_app_render.sql."""
    here = pathlib.Path(__file__).resolve()
    repo = here.parents[3]
    mig = (
        repo
        / "packages/kerf-core/src/kerf_core/db/migrations/0010_github_app_render.sql"
    )
    sql = mig.read_text()
    assert "CREATE TABLE IF NOT EXISTS render_jobs" in sql
    assert "CREATE INDEX IF NOT EXISTS render_jobs_status_idx" in sql


# ---------------------------------------------------------------------------
# submit_job
# ---------------------------------------------------------------------------


def test_submit_job_inserts_queued():
    pool = FakePool()
    jid = run(submit_job(
        pool, user_id="u1", scene_blob_hash="abc", preset="hero"
    ))
    row = pool.rows[jid]
    assert row["status"] == "queued"
    assert row["samples_total"] == PRESET_SAMPLES["hero"]
    assert row["samples_done"] == 0


def test_submit_job_unknown_preset_normalises():
    pool = FakePool()
    jid = run(submit_job(
        pool, user_id="u1", scene_blob_hash="abc", preset="bogus"
    ))
    assert pool.rows[jid]["preset"] == "standard"


def test_submit_job_explicit_id_respected():
    pool = FakePool()
    jid = run(submit_job(
        pool, user_id="u1", scene_blob_hash="h", job_id="fixed-id-1"
    ))
    assert jid == "fixed-id-1"
    assert "fixed-id-1" in pool.rows


# ---------------------------------------------------------------------------
# get_job_status
# ---------------------------------------------------------------------------


def test_get_job_status_none_when_missing():
    pool = FakePool()
    assert run(get_job_status(pool, "nope")) is None


def test_get_job_status_mirrors_columns():
    pool = FakePool()
    jid = run(submit_job(pool, user_id="u1", scene_blob_hash="h", preset="draft"))
    st = run(get_job_status(pool, jid))
    assert st["id"] == jid
    assert st["status"] == "queued"
    assert st["preset"] == "draft"
    assert st["samples_total"] == PRESET_SAMPLES["draft"]


# ---------------------------------------------------------------------------
# Lifecycle transitions
# ---------------------------------------------------------------------------


def test_full_lifecycle_to_complete():
    pool = FakePool()
    jid = run(submit_job(pool, user_id="u1", scene_blob_hash="h", preset="hero"))

    run(mark_rendering(pool, jid, PRESET_SAMPLES["hero"]))
    assert run(get_job_status(pool, jid))["status"] == "rendering"

    run(update_progress(pool, jid, 1024))
    assert run(get_job_status(pool, jid))["samples_done"] == 1024

    run(mark_complete(pool, jid, "https://cdn/result.png"))
    st = run(get_job_status(pool, jid))
    assert st["status"] == "complete"
    assert st["signed_url"] == "https://cdn/result.png"
    assert st["samples_done"] == st["samples_total"]


def test_mark_failed_records_error_truncated():
    pool = FakePool()
    jid = run(submit_job(pool, user_id="u1", scene_blob_hash="h"))
    long_err = "E" * 5000
    run(mark_failed(pool, jid, long_err))
    st = run(get_job_status(pool, jid))
    assert st["status"] == "failed"
    assert len(st["error"]) == 2000


# ---------------------------------------------------------------------------
# cancel_job
# ---------------------------------------------------------------------------


def test_cancel_queued_job_succeeds():
    pool = FakePool()
    jid = run(submit_job(pool, user_id="u1", scene_blob_hash="h"))
    assert run(cancel_job(pool, jid)) is True
    assert run(get_job_status(pool, jid))["status"] == "cancelled"


def test_cancel_terminal_job_is_noop():
    pool = FakePool()
    jid = run(submit_job(pool, user_id="u1", scene_blob_hash="h"))
    run(mark_complete(pool, jid, "url"))
    assert run(cancel_job(pool, jid)) is False
    assert run(get_job_status(pool, jid))["status"] == "complete"


def test_cancel_missing_job_returns_false():
    pool = FakePool()
    assert run(cancel_job(pool, "ghost")) is False
