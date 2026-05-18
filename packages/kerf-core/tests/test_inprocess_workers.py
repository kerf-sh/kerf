"""In-process worker co-location (single app = engine + workers).

Pins the contract behind the one-instance-group deploy:

  * _maybe_start_inprocess_workers is OFF unless KERF_INPROCESS_WORKERS
    is truthy, and never raises / never blocks app boot (returns None
    when disabled or when there is no DB pool).
  * InProcessWorkers runs the worker harness as background tasks and
    aclose() cleanly stops them — with NO OS signal handlers (uvicorn
    owns signals in the co-located process).
  * Zero configured workers is a clean no-op.

The separation path (standalone `python -m kerf_workers.runner`) shares
_build_workers() with the in-process path, so this also guards against
the two diverging.
"""
import asyncio
import types

import pytest

from kerf_core.app import _maybe_start_inprocess_workers


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _fake_app(pool=None):
    app = types.SimpleNamespace()
    app.state = types.SimpleNamespace()
    if pool is not None:
        app.state.pool = pool
    app.state.storage = object()
    return app


def test_disabled_by_default_returns_none(monkeypatch):
    monkeypatch.delenv("KERF_INPROCESS_WORKERS", raising=False)
    assert _run(_maybe_start_inprocess_workers(_fake_app(pool=object()))) is None


def test_enabled_but_no_pool_is_safe_noop(monkeypatch):
    monkeypatch.setenv("KERF_INPROCESS_WORKERS", "true")
    # No app.state.pool -> must not raise, must not block boot.
    assert _run(_maybe_start_inprocess_workers(_fake_app(pool=None))) is None


def test_zero_workers_is_clean_noop(monkeypatch):
    from kerf_workers import runner
    from kerf_workers.runner import InProcessWorkers, _build_workers

    # All JOB-worker counts 0 → only the always-on PricingRefreshWorker
    # remains (it keeps model_prices current; intentionally never zero).
    workers = _build_workers(
        pool=object(), storage_getter=lambda: None,
        fem_count=0, sim_count=0, tess_count=0, cam_count=0,
        compaction_count=0, cloud_enabled=False, local_mode=True,
    )
    assert [type(w).__name__ for w in workers] == ["PricingRefreshWorker"]

    # A truly empty harness → InProcessWorkers is a clean no-op (no task).
    monkeypatch.setattr(runner, "_build_workers", lambda *a, **k: [])
    handle = _run(InProcessWorkers.start(pool=object(), storage_getter=lambda: None))
    _run(handle.aclose())


def test_start_runs_and_aclose_stops_workers(monkeypatch):
    """Lifecycle: workers run as background tasks; aclose() stops them.

    Uses a fake worker (no heavy compute deps) injected via _build_workers
    so the TaskGroup start + cooperative-stop path is exercised directly.
    """
    from kerf_workers import runner

    class FakeWorker:
        def __init__(self):
            self.started = False
            self.stopped = False
            self._ev = asyncio.Event()

        async def run(self, tg):
            self.started = True
            await self._ev.wait()

        def stop(self):
            self.stopped = True
            self._ev.set()

    fw = FakeWorker()
    monkeypatch.setattr(runner, "_build_workers", lambda *a, **k: [fw])

    async def scenario():
        handle = await runner.InProcessWorkers.start(
            pool=object(), storage_getter=lambda: None,
        )
        # let the background task schedule the worker
        for _ in range(50):
            if fw.started:
                break
            await asyncio.sleep(0.01)
        assert fw.started, "worker did not start in-process"
        assert not fw.stopped
        await handle.aclose(timeout=5)
        assert fw.stopped, "aclose() must cooperatively stop workers"

    _run(scenario())
