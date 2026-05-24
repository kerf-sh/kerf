"""Regression: fly.toml must run migrations in `[deploy] release_command`.

# Fly-specific, see deployment/fly.md
#
# The hosted Koyeb deployment uses `pre_deploy_command` in koyeb.yaml for the
# same invariant; see test_release_command.py for the host-agnostic runner
# tests.  This file stays so the self-host Fly path can't regress silently.

Without release_command, migrations land via `flyctl ssh console -C ...`
AFTER `flyctl deploy` returns. By then the new machine has already booted
its in-process workers (KERF_INPROCESS_WORKERS=true) and they immediately
poll fem_jobs / sim_jobs / step_tessellation_jobs / model_prices —
crashing with UndefinedTableError until the post-deploy migration step
catches up tens of seconds later. The git panel (and any other endpoint
reading from a yet-to-be-created table) returns 500 in that window.

This test pins the [deploy] block so a refactor can't silently regress.
"""
import pathlib

_FLY = (
    pathlib.Path(__file__).resolve().parents[3] / "fly.toml"
).read_text()


def test_fly_toml_has_deploy_release_command():
    assert "[deploy]" in _FLY
    assert "release_command" in _FLY


def test_release_command_runs_the_migration_runner():
    # Must invoke the runner module; pinning the exact module path so
    # rename-without-update fails the test loudly.
    assert "kerf_core.db.migrations.runner" in _FLY


def test_inprocess_workers_still_default_to_true():
    # If workers ever default off, the release_command race no longer
    # matters and this test can be relaxed. Until then, in-process
    # workers + race → outage, so this is the invariant we're protecting.
    assert 'KERF_INPROCESS_WORKERS = "true"' in _FLY
