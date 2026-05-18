"""BYO-Blender path tests for T-106e self-host docker image.

Tests verify the environment-variable contract that the worker honours when
dispatching render subprocesses.  All Blender calls are mocked — no live
Blender binary or Docker daemon is required.

Covered:

  - ``resolve_blender_bin`` reads ``KERF_BLENDER_PATH=/fake/blender`` and
    returns it as the binary to use.
  - ``resolve_blender_bin`` prefers ``KERF_BLENDER_BIN`` (set by entrypoint)
    over ``KERF_BLENDER_PATH``.
  - ``resolve_blender_bin`` falls back to ``"blender"`` when neither env var
    is set.
  - ``run_blender`` passes the resolved binary as ``argv[0]`` to subprocess.
  - ``CyclesWorkerConfig.blender_path`` defaults to ``"blender"``, and the
    worker respects ``KERF_BLENDER_PATH`` when it is set at instantiation time
    via ``resolve_blender_bin``.
  - Docker build / live-run tests are skipped when ``docker`` is not on PATH.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Import the module under test (cycles_worker must already be landed — T-106b)
# ---------------------------------------------------------------------------

from kerf_render.cycles_worker import (
    CyclesWorkerConfig,
    resolve_blender_bin,
    run_blender,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_completed(returncode: int = 0) -> subprocess.CompletedProcess:
    """Return a synthetic CompletedProcess suitable for mock targets."""
    return subprocess.CompletedProcess(
        args=[],
        returncode=returncode,
        stdout="Blender 4.1.1 (hash abc)",
        stderr="",
    )


# ---------------------------------------------------------------------------
# resolve_blender_bin — env-var precedence
# ---------------------------------------------------------------------------

class TestResolveBin:
    """Verify env-var precedence for Blender binary resolution."""

    def test_byo_path_returned_when_set(self):
        """KERF_BLENDER_PATH=/fake/blender is returned verbatim."""
        env = {"KERF_BLENDER_PATH": "/fake/blender"}
        # Clear KERF_BLENDER_BIN so only KERF_BLENDER_PATH is active.
        with patch.dict(os.environ, {}, clear=True):
            os.environ.update(env)
            result = resolve_blender_bin()
        assert result == "/fake/blender"

    def test_bundled_bin_env_takes_precedence_over_byo_path(self):
        """KERF_BLENDER_BIN (set by entrypoint) wins over KERF_BLENDER_PATH."""
        env = {
            "KERF_BLENDER_BIN":  "/opt/blender/blender",
            "KERF_BLENDER_PATH": "/fake/blender",
        }
        with patch.dict(os.environ, env, clear=True):
            result = resolve_blender_bin()
        assert result == "/opt/blender/blender"

    def test_fallback_when_neither_var_set(self):
        """Falls back to bare 'blender' when no env vars are present."""
        with patch.dict(os.environ, {}, clear=True):
            result = resolve_blender_bin()
        assert result == "blender"

    def test_empty_byo_path_does_not_override_fallback(self):
        """An empty string value for KERF_BLENDER_PATH is ignored."""
        with patch.dict(os.environ, {"KERF_BLENDER_PATH": "", "KERF_BLENDER_BIN": ""}, clear=True):
            result = resolve_blender_bin()
        assert result == "blender"

    def test_byo_path_with_spaces_returned_verbatim(self):
        """macOS .app bundle paths that include spaces are returned as-is."""
        byo = "/Applications/Blender 4.app/Contents/MacOS/Blender"
        with patch.dict(os.environ, {"KERF_BLENDER_PATH": byo, "KERF_BLENDER_BIN": ""}, clear=True):
            result = resolve_blender_bin()
        assert result == byo


# ---------------------------------------------------------------------------
# run_blender — subprocess call shape
# ---------------------------------------------------------------------------

class TestRunBlender:
    """Verify that run_blender calls subprocess.run with the correct argv."""

    def test_byo_path_used_as_argv0(self, tmp_path):
        """KERF_BLENDER_PATH is propagated to subprocess argv[0]."""
        script = tmp_path / "scene.py"
        script.write_text("# stub")
        byo = "/fake/blender"
        with patch("subprocess.run", return_value=_fake_completed()) as mock_run:
            run_blender(str(script), blender_bin=byo)
        argv = mock_run.call_args[0][0]
        assert argv[0] == byo

    def test_env_byo_path_used_when_blender_bin_not_supplied(self, tmp_path):
        """When blender_bin kwarg is None, KERF_BLENDER_PATH env var is used."""
        script = tmp_path / "env_byo.py"
        script.write_text("# stub")
        byo = "/fake/blender"
        with patch.dict(os.environ, {"KERF_BLENDER_PATH": byo, "KERF_BLENDER_BIN": ""}, clear=True):
            with patch("subprocess.run", return_value=_fake_completed()) as mock_run:
                run_blender(str(script))
        argv = mock_run.call_args[0][0]
        assert argv[0] == byo

    def test_headless_flag_always_present(self, tmp_path):
        """-b (background/headless) must always appear in the subprocess argv."""
        script = tmp_path / "headless.py"
        script.write_text("# stub")
        with patch("subprocess.run", return_value=_fake_completed()) as mock_run:
            run_blender(str(script), blender_bin="/fake/blender")
        argv = mock_run.call_args[0][0]
        assert "-b" in argv

    def test_python_script_flag_present(self, tmp_path):
        """--python <path> must appear so Blender executes the render script."""
        script = tmp_path / "render.py"
        script.write_text("# stub")
        with patch("subprocess.run", return_value=_fake_completed()) as mock_run:
            run_blender(str(script), blender_bin="/fake/blender")
        argv = mock_run.call_args[0][0]
        assert "--python" in argv
        assert str(script) in argv

    def test_noaudio_flag_present(self, tmp_path):
        """-noaudio suppresses audio device initialisation in headless mode."""
        script = tmp_path / "noaudio.py"
        script.write_text("# stub")
        with patch("subprocess.run", return_value=_fake_completed()) as mock_run:
            run_blender(str(script), blender_bin="/fake/blender")
        argv = mock_run.call_args[0][0]
        assert "-noaudio" in argv

    def test_returncode_propagated(self, tmp_path):
        """A non-zero Blender exit code is surfaced to the caller unchanged."""
        script = tmp_path / "fail.py"
        script.write_text("# stub")
        with patch("subprocess.run", return_value=_fake_completed(returncode=1)):
            result = run_blender(str(script), blender_bin="/fake/blender")
        assert result.returncode == 1

    def test_subprocess_timeout_is_positive(self, tmp_path):
        """subprocess.run must be invoked with a finite positive timeout."""
        script = tmp_path / "timeout.py"
        script.write_text("# stub")
        with patch("subprocess.run", return_value=_fake_completed()) as mock_run:
            run_blender(str(script), blender_bin="/fake/blender")
        kwargs = mock_run.call_args[1]
        assert "timeout" in kwargs, "timeout kwarg missing from subprocess.run call"
        assert kwargs["timeout"] > 0

    def test_capture_output_enabled(self, tmp_path):
        """stdout and stderr must be captured so the worker can report errors."""
        script = tmp_path / "capture.py"
        script.write_text("# stub")
        with patch("subprocess.run", return_value=_fake_completed()) as mock_run:
            run_blender(str(script), blender_bin="/fake/blender")
        kwargs = mock_run.call_args[1]
        captured = kwargs.get("capture_output") is True or (
            "stdout" in kwargs and "stderr" in kwargs
        )
        assert captured, "subprocess.run must capture stdout/stderr"


# ---------------------------------------------------------------------------
# CyclesWorkerConfig — blender_path wiring
# ---------------------------------------------------------------------------

class TestWorkerConfig:
    """Verify that CyclesWorkerConfig reflects the BYO env-var contract."""

    def test_default_blender_path_is_blender(self):
        """Default config uses the bare 'blender' command (resolved from PATH)."""
        cfg = CyclesWorkerConfig()
        assert cfg.blender_path == "blender"

    def test_custom_blender_path_stored(self):
        """An explicit blender_path is stored and retrievable."""
        cfg = CyclesWorkerConfig(blender_path="/fake/blender")
        assert cfg.blender_path == "/fake/blender"

    def test_resolve_blender_bin_respects_config_path(self, tmp_path):
        """When a caller passes the resolved path to the config, it is honoured.

        This mirrors the typical integration pattern:
          cfg = CyclesWorkerConfig(blender_path=resolve_blender_bin())
        """
        byo = "/fake/blender"
        with patch.dict(os.environ, {"KERF_BLENDER_PATH": byo, "KERF_BLENDER_BIN": ""}, clear=True):
            cfg = CyclesWorkerConfig(blender_path=resolve_blender_bin())
        assert cfg.blender_path == byo


# ---------------------------------------------------------------------------
# Docker availability guard — live build/run tests
# ---------------------------------------------------------------------------

_docker_available = shutil.which("docker") is not None


@pytest.mark.skipif(not _docker_available, reason="docker not on PATH")
class TestDockerSmoke:
    """Smoke-level Docker tests.  Skipped when Docker is not installed."""

    def test_docker_is_callable(self):
        """Sanity: `docker info` exits 0 when the daemon is running."""
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert result.returncode == 0, (
            f"docker info failed (daemon may not be running):\n{result.stderr}"
        )
