import subprocess
import tempfile
import os
from pathlib import Path


class FreeRouter:
    def __init__(self, jar_path: str = "FreeRouting.jar"):
        self.jar = jar_path

    def route(
        self,
        dsn_input: str,
        trace_width: float = 0.2,
        via_diameter: float = 0.6,
        via_drill: float = 0.3,
        clearance: float = 0.2,
        layers: list[str] | None = None,
        cost_dihedral: float = 90.0,
        cost_via: float = 50.0,
    ) -> str:
        if layers is None:
            layers = ["1top", "16bot"]

        with tempfile.TemporaryDirectory() as tmpdir:
            dsn_path = Path(tmpdir) / "input.dsn"
            ses_path = Path(tmpdir) / "output.ses"

            dsn_path.write_text(dsn_input)

            cmd = self._build_command(
                str(dsn_path),
                str(ses_path),
                trace_width,
                via_diameter,
                via_drill,
                clearance,
                layers,
                cost_dihedral,
                cost_via,
            )

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

            return ses_path.read_text()

    def _build_command(
        self,
        dsn_path: str,
        ses_path: str,
        trace_width: float,
        via_diameter: float,
        via_drill: float,
        clearance: float,
        layers: list[str],
        cost_dihedral: float,
        cost_via: float,
    ) -> list[str]:
        java_trace_width_mils = trace_width * 39.3701
        java_via_dia_mils = via_diameter * 39.3701
        java_via_drill_mils = via_drill * 39.3701
        java_clearance_mils = clearance * 39.3701

        cmd = [
            "java",
            "-jar",
            self.jar,
            "-c",
            f"route_width={java_trace_width_mils}",
            f"via_diameter={java_via_dia_mils}",
            f"via_drill={java_via_drill_mils}",
            f"clearance={java_clearance_mils}",
            f"cost_via={cost_via}",
            f"cost_dihedral={cost_dihedral}",
            "-layers",
            ",".join(layers),
            "-only_routing",
            "-force_fanout",
            "on",
        ]

        cmd.extend(["-from", dsn_path, "-to", ses_path])

        return cmd
