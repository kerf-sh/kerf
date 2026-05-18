"""kerf-billing plugin entry-point.

Cloud-gated: when ctx.cloud_enabled is False, returns an empty manifest and
no routes are mounted.
"""
from __future__ import annotations

import logging
import os
import asyncio
from datetime import datetime
from typing import Optional

from fastapi import FastAPI

from kerf_core.plugin import PluginManifest

# >>> CLOUD-BETA (remove post-launch): drop this import when beta.py is deleted.
from kerf_billing.billing.beta import payments_disabled
# <<< CLOUD-BETA

PLUGIN_DEPENDS = ["kerf-auth"]

_log = logging.getLogger(__name__)


class _MultiProjectOracle:
    """Adapter that satisfies the GitReachabilityOracle Protocol for all projects.

    The concrete ``GitReachabilityOracle`` operates on a single bare repo dir.
    GC, however, works across all projects — an oid may be referenced from any
    project's repo.  This adapter enumerates all project repos by scanning the
    storage root (LocalStorage: ``workspaces/*/git``) and returns True if *any*
    project repo considers the oid reachable.

    For S3 storage the walk is best-effort: we scan any local working-copy dirs
    already present under the default temp-dir prefix.  Repos not yet cloned
    are skipped (safe: we return True by default when we cannot confirm
    unreachability — see the per-repo error handling in ConcreteOracle).
    """

    def __init__(self, storage, oracle_cls) -> None:
        self._storage = storage
        self._oracle_cls = oracle_cls

    def _candidate_repo_dirs(self) -> list[str]:
        """Yield all on-disk bare repo dirs that currently exist."""
        root = getattr(self._storage, "root", None)
        if root is not None:
            # LocalStorage: repos live at <root>/workspaces/<pid>/git
            workspaces_dir = os.path.join(str(root), "workspaces")
            if not os.path.isdir(workspaces_dir):
                return []
            dirs: list[str] = []
            try:
                for pid_entry in os.scandir(workspaces_dir):
                    if not pid_entry.is_dir():
                        continue
                    git_dir = os.path.join(pid_entry.path, "git")
                    if os.path.isdir(git_dir):
                        dirs.append(git_dir)
            except OSError:
                pass
            return dirs

        # S3 or unknown: scan the standard temp working-copy dir for any
        # *.git directories that have been cloned locally.
        import tempfile
        base = os.path.join(tempfile.gettempdir(), "kerf-git-worktrees")
        if not os.path.isdir(base):
            return []
        dirs = []
        try:
            for entry in os.scandir(base):
                if entry.is_dir() and entry.name.endswith(".git"):
                    dirs.append(entry.path)
        except OSError:
            pass
        return dirs

    def is_oid_reachable(self, oid: str) -> bool:
        for repo_dir in self._candidate_repo_dirs():
            oracle = self._oracle_cls(repo_dir)
            if oracle.is_oid_reachable(oid):
                return True
        return False

    def last_unreachable_at(self, oid: str) -> Optional[datetime]:
        return None


async def register(app: FastAPI, ctx) -> PluginManifest:
    if not ctx.cloud_enabled:
        ctx.logger.info("kerf-billing: cloud_enabled=False — plugin dormant")
        return PluginManifest(
            name="kerf-billing",
            version="0.1.0",
            provides=[],
            depends=["kerf-auth"],
        )

    # >>> CLOUD-BETA (remove post-launch): delete this block; always mount
    # the full Paystack router and init Paystack unconditionally below.
    settings = getattr(ctx, "settings", None) or getattr(ctx, "cfg", None)
    if payments_disabled(settings):
        from kerf_billing.routes import router_beta_inert
        app.include_router(router_beta_inert, prefix="/api", tags=["billing"])
        ctx.logger.info(
            "kerf-billing: cloud_beta=True — Paystack routes inert (503), "
            "no PaystackClient constructed"
        )
        return PluginManifest(
            name="kerf-billing",
            version="0.1.0",
            # >>> CLOUD-BETA (remove post-launch): restore "billing.paystack" below.
            provides=["billing.buckets"],
            # <<< CLOUD-BETA
            depends=["kerf-auth"],
        )
    # <<< CLOUD-BETA

    from kerf_billing.routes import router
    app.include_router(router, prefix="/api", tags=["billing"])

    ctx.logger.info("kerf-billing: registered /api/billing/* routes (Paystack)")

    # ── Background BillingResetWorker — daily api-token cap reset + monthly
    # free-quota reset.  Only registered when running in cloud mode.
    workers_registry = getattr(ctx, "workers", None)
    if workers_registry is not None and not ctx.local_mode:
        try:
            from kerf_billing.scheduler import BillingResetWorker

            async def _factory():
                return BillingResetWorker(pool=ctx.pool)

            workers_registry.register("billing_reset", _factory)
            ctx.logger.info("kerf-billing: BillingResetWorker registered")
        except Exception as exc:
            ctx.logger.warning(
                "kerf-billing: failed to register BillingResetWorker: %s", exc
            )

        # ── BlobGCWorker — storage GC sweep (T-136).
        # Dry-run by default; physical deletes require BLOB_GC_DRY_RUN=false
        # AND a GitReachabilityOracle wired in.
        try:
            from kerf_billing.blob_gc import BlobGCWorker, _dry_run_from_env
            from kerf_core.storage.git_reachability import (
                GitReachabilityOracle as ConcreteOracle,
            )

            storage = getattr(ctx, "storage", None)
            if storage is not None:
                async def _gc_factory():
                    worker = BlobGCWorker(
                        pool=ctx.pool,
                        storage=storage,
                        dry_run=_dry_run_from_env(),
                    )

                    # Wire the concrete oracle.  The oracle walks bare repos
                    # whose location is derived from the storage backend root
                    # (LocalStorage) or a temp working copy (S3).  We pass the
                    # storage object to resolve_project_repo at query time
                    # inside a thin per-project wrapper so the single
                    # GitReachabilityOracle instance used here works across all
                    # projects.
                    oracle = _MultiProjectOracle(storage, ConcreteOracle)
                    worker.set_oracle(oracle)
                    ctx.logger.info("kerf-billing: BlobGCWorker oracle=GitReachabilityOracle")
                    return worker

                workers_registry.register("blob_gc", _gc_factory)
                ctx.logger.info("kerf-billing: BlobGCWorker registered")
            else:
                ctx.logger.warning(
                    "kerf-billing: BlobGCWorker skipped — ctx.storage is None"
                )
        except Exception as exc:
            ctx.logger.warning(
                "kerf-billing: failed to register BlobGCWorker: %s", exc
            )

    return PluginManifest(
        name="kerf-billing",
        version="0.1.0",
        provides=["billing.paystack", "billing.buckets"],
        depends=["kerf-auth"],
    )
