"""Regression: migration runner CLI must accept DATABASE_URL env fallback.

The Koyeb pre-deploy migration job (scripts/deploy-koyeb.sh) relies on the
runner reading the DSN from the environment — it can't inject secrets directly
into the command string. We moved migrations into this pre-deploy hook to
fix the race where in-process workers booted and crashed on UndefinedTableError
(fem_jobs / sim_jobs / step_tessellation_jobs / model_prices) before a
post-deploy manual migration step could land.

To support that, the runner now reads from argv[1] OR $DATABASE_URL.
This test pins both behaviours and is host-agnostic.
"""
import pathlib
import subprocess
import sys

_RUNNER = pathlib.Path(__file__).resolve().parents[1] / "src/kerf_core/db/migrations/runner.py"


def _run(env: dict, args: list[str]) -> tuple[int, str, str]:
    """Invoke the runner as a CLI; capture exit + stdout + stderr.

    Uses python -m so the relative imports work; the test only exercises
    the argv-parsing / env-fallback front door, not the actual DB run.
    """
    proc = subprocess.run(
        [sys.executable, "-m", "kerf_core.db.migrations.runner", *args],
        capture_output=True,
        text=True,
        env={**env, "PYTHONPATH": str(_RUNNER.parents[4])},
    )
    return proc.returncode, proc.stdout, proc.stderr


def test_no_args_and_no_env_prints_usage_and_exits_nonzero():
    """No argv[1] and no $DATABASE_URL → usage message, exit 1."""
    env = {"PATH": "/usr/bin:/bin"}  # deliberately strip DATABASE_URL
    code, out, _ = _run(env, [])
    assert code != 0
    assert "Usage" in out
    assert "DATABASE_URL" in out


def test_database_url_env_is_picked_up():
    """$DATABASE_URL alone (no argv[1]) → runner attempts to connect.

    We can't run real migrations in this test environment (no Postgres),
    but we can prove the runner *tried* to use the env DSN by giving it
    an unreachable host and asserting the error is a connection failure
    (not a "Usage" message — which would mean the env wasn't read).
    """
    env = {
        "PATH": "/usr/bin:/bin",
        # Intentional sentinel — non-routable IP so we get a connection
        # failure quickly, proving the DSN was picked up.
        "DATABASE_URL": "postgres://x:x@127.0.0.1:1/x",
    }
    code, out, err = _run(env, [])
    assert code != 0
    # "Usage" would mean env wasn't read; we want a connection-attempt error.
    assert "Usage" not in out
    combined = (out + err).lower()
    assert any(
        token in combined
        for token in ["connect", "refused", "timeout", "could not", "asyncpg", "oserror"]
    ), f"expected a connection-attempt error, got:\nstdout={out!r}\nstderr={err!r}"


def test_argv_dsn_still_works():
    """Explicit `python -m runner <dsn>` path (used by self-host scripts that
    pass the DSN directly) must still work — env is the alternative, not the
    replacement."""
    env = {"PATH": "/usr/bin:/bin"}  # no DATABASE_URL
    code, out, err = _run(env, ["postgres://x:x@127.0.0.1:1/x"])
    assert code != 0
    assert "Usage" not in out
    combined = (out + err).lower()
    assert any(
        token in combined
        for token in ["connect", "refused", "timeout", "could not", "asyncpg", "oserror"]
    ), f"expected a connection-attempt error, got:\nstdout={out!r}\nstderr={err!r}"
