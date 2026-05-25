"""Regression: deploy-koyeb.sh must run migrations BEFORE traffic shifts.

The Koyeb cutover (Fly.io → Koyeb migration) replaced Fly's
`[deploy] release_command` with a one-off Koyeb migration job dispatched by
`scripts/deploy-koyeb.sh`. The invariant is unchanged: migrations must finish
before the new engine revision takes traffic, or in-process workers boot and
crash on UndefinedTableError (fem_jobs / sim_jobs / step_tessellation_jobs /
model_prices) against an un-migrated schema.

This pins that the deploy script (a) invokes the migration runner, (b) blocks
on it (`--wait`), and (c) does so before the engine `service deploy`.
"""
import pathlib

_DEPLOY = (
    pathlib.Path(__file__).resolve().parents[3] / "scripts/deploy-koyeb.sh"
)


def _script() -> str:
    return _DEPLOY.read_text()


def test_deploy_koyeb_script_exists():
    assert _DEPLOY.is_file(), "scripts/deploy-koyeb.sh must exist (Koyeb is the hosted-tier deploy path)"


def test_runs_migration_runner_before_service_deploy():
    src = _script()
    # (a) the migration runner is invoked
    assert "kerf_core.db.migrations.runner" in src, (
        "deploy-koyeb.sh must run the migration runner as a pre-deploy job"
    )
    # (b) it blocks until the migration completes
    mig_idx = src.index("kerf_core.db.migrations.runner")
    job_block = src[max(0, mig_idx - 400):mig_idx + 400]
    assert "--wait" in job_block, (
        "the migration job must use --wait so the deploy blocks until migrations finish"
    )
    # (c) migration happens before the engine service takes traffic
    deploy_idx = src.find("service deploy engine")
    assert deploy_idx != -1, "deploy-koyeb.sh must deploy the engine service"
    assert mig_idx < deploy_idx, (
        "migrations must run BEFORE 'koyeb service deploy engine' — otherwise the "
        "new revision boots against an un-migrated DB"
    )
