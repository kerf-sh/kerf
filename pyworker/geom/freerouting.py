"""
FreeRouter integration — wraps the FreeRouting JAR as a subprocess.

FreeRouting is a free, open-source auto-router originally developed for the
FreePCB project and later extracted. It reads Specctra DSN files and writes
Specctra SES session files. Kerf uses it to auto-route PCB traces from
tscircuit CircuitJSON.

Jar download: https://github.com/freerouting/freerouting/releases
Default cache: ~/.cache/kerf/freerouting/FreeRouting.jar
Requires: Java 17+
"""

import os
import subprocess
import tempfile
from pathlib import Path

_JAR_URL = (
    "https://github.com/freerouting/freerouting/releases/download/"
    "v1.9.0/freerouting-1.9.0-executable.jar"
)
_JAR_CACHE_DIR = Path.home() / ".cache" / "kerf" / "freerouting"
_JAR_CACHE_PATH = _JAR_CACHE_DIR / "FreeRouting.jar"


def _download_jar(dest: Path) -> None:
    """Download the FreeRouting JAR to dest. Raises RuntimeError on failure."""
    import urllib.request

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp")
    try:
        urllib.request.urlretrieve(_JAR_URL, str(tmp))
        tmp.rename(dest)
    except Exception as exc:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        raise RuntimeError(
            f"FreeRouting JAR download failed: {exc}. "
            f"Install manually: download {_JAR_URL} to {dest}"
        ) from exc


class FreeRouter:
    """
    Wraps the FreeRouting JAR as a subprocess.

    Usage::

        router = FreeRouter()  # auto-resolves jar
        ses_output = router.route(dsn_string)

    Parameters
    ----------
    jar_path : str or None
        Explicit path to FreeRouting.jar. If None (default), the jar is
        resolved from ~/.cache/kerf/freerouting/FreeRouting.jar, and
        downloaded on first use if not present.
    """

    def __init__(self, jar_path: str | None = None):
        if jar_path is not None:
            self.jar = jar_path
        else:
            self.jar = None  # lazy-resolved via _ensure_jar()

    def _ensure_jar(self) -> str:
        """Resolve or download the FreeRouting JAR. Returns the path."""
        if self.jar is not None:
            return self.jar

        if _JAR_CACHE_PATH.exists():
            self.jar = str(_JAR_CACHE_PATH)
            return self.jar

        _download_jar(_JAR_CACHE_PATH)
        self.jar = str(_JAR_CACHE_PATH)
        return self.jar

    def route(
        self,
        dsn_input: str,
        trace_width: float = 0.2,
        via_diameter: float = 0.6,
        via_drill: float = 0.3,
        clearance: float = 0.2,
        layers: list | None = None,
        cost_dihedral: float = 90.0,
        cost_via: float = 50.0,
        num_passes: int = 3,
        max_vias: int | None = None,
        progress_callback=None,
    ) -> str:
        """
        Run FreeRouting on a DSN string and return the SES output string.

        Parameters
        ----------
        dsn_input : str
            Specctra DSN content to route.
        trace_width : float
            Trace width in mm.
        via_diameter : float
            Via pad diameter in mm.
        via_drill : float
            Via drill diameter in mm.
        clearance : float
            Minimum clearance in mm.
        layers : list[str] or None
            Layer names, e.g. ["1top", "16bot"]. Defaults to 2-layer board.
        cost_dihedral : float
            Angle change cost (higher = prefers straight routes).
        cost_via : float
            Via placement cost (higher = fewer vias).
        num_passes : int
            Number of routing passes (default 3).
        max_vias : int or None
            Via budget cap. None = unlimited.
        progress_callback : callable or None
            Called with each stdout/stderr line as routing progresses.
            Signature: callback(line: str) -> None

        Returns
        -------
        str
            Specctra SES session file content.
        """
        if layers is None:
            layers = ["1top", "16bot"]

        jar = self._ensure_jar()

        with tempfile.TemporaryDirectory() as tmpdir:
            dsn_path = Path(tmpdir) / "input.dsn"
            ses_path = Path(tmpdir) / "output.ses"

            dsn_path.write_text(dsn_input, encoding="utf-8")

            cmd = self._build_command(
                str(dsn_path),
                str(ses_path),
                jar,
                trace_width,
                via_diameter,
                via_drill,
                clearance,
                layers,
                cost_dihedral,
                cost_via,
                num_passes,
                max_vias,
            )

            if progress_callback is not None:
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    cwd=tmpdir,
                )
                try:
                    for line in proc.stdout:
                        line = line.rstrip()
                        if line:
                            try:
                                progress_callback(line)
                            except Exception:
                                pass
                    returncode = proc.wait(timeout=600)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                    raise RuntimeError("FreeRouting timed out after 600s")
                if returncode != 0:
                    raise RuntimeError(f"FreeRouting exited with code {returncode}")
            else:
                try:
                    result = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        timeout=600,
                        cwd=tmpdir,
                    )
                except subprocess.TimeoutExpired:
                    raise RuntimeError("FreeRouting timed out after 600s")

                if result.returncode != 0:
                    stderr = result.stderr or ""
                    raise RuntimeError(f"FreeRouting failed: {stderr[:500]}")

            if not ses_path.exists():
                raise RuntimeError("FreeRouting did not produce SES output")

            return ses_path.read_text(encoding="utf-8")

    def _build_command(
        self,
        dsn_path: str,
        ses_path: str,
        jar: str,
        trace_width: float,
        via_diameter: float,
        via_drill: float,
        clearance: float,
        layers: list,
        cost_dihedral: float,
        cost_via: float,
        num_passes: int,
        max_vias: int | None,
    ) -> list:
        # FreeRouting uses mils internally (1 mm = 39.3701 mils)
        mm_to_mils = 39.3701
        tw_mils = trace_width * mm_to_mils
        vd_mils = via_diameter * mm_to_mils
        vdrill_mils = via_drill * mm_to_mils
        cl_mils = clearance * mm_to_mils

        cmd = [
            "java",
            "-jar",
            jar,
            "-c",
            f"route_width={tw_mils:.2f}",
            f"via_diameter={vd_mils:.2f}",
            f"via_drill={vdrill_mils:.2f}",
            f"clearance={cl_mils:.2f}",
            f"cost_via={cost_via:.1f}",
            f"cost_dihedral={cost_dihedral:.1f}",
            f"passes={num_passes}",
        ]

        if max_vias is not None:
            cmd.append(f"max_vias={int(max_vias)}")

        cmd += [
            "-layer-count",
            str(len(layers)),
            "-layers",
            ",".join(layers),
            "-only_routing",
            "-force_fanout",
            "on",
            "-from",
            dsn_path,
            "-to",
            ses_path,
        ]

        return cmd
