"""OpenLane config.json generator.

Produces an OpenLane-compatible config.json for a design.  The JSON schema
follows the OpenLane 2 / sky130A convention:

    {
      "DESIGN_NAME": "my_adder",
      "VERILOG_FILES": ["rtl/my_adder.v"],
      "CLOCK_PORT": "clk",
      "CLOCK_PERIOD": 10.0,
      "PDK": "sky130A",
      "DIE_AREA": [0, 0, 100, 100]
    }
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional, Tuple


def build_config(
    design_name: str,
    verilog_files: List[str],
    *,
    clock_port: str = "clk",
    clock_period: float = 10.0,
    pdk: str = "sky130A",
    die_area: Tuple[float, float, float, float] = (0, 0, 100, 100),
) -> dict:
    """Return an OpenLane config dict for the given design parameters.

    Args:
        design_name:   Top-level module / design name.
        verilog_files: List of Verilog source file paths (relative or absolute).
        clock_port:    Primary clock port name.
        clock_period:  Clock period in nanoseconds (default 10.0 ns → 100 MHz).
        pdk:           Process design kit identifier (default "sky130A").
        die_area:      Die bounding box as (x0, y0, x1, y1) in micrometres.

    Returns:
        dict suitable for ``json.dumps``.
    """
    if not design_name:
        raise ValueError("design_name must not be empty")
    if not verilog_files:
        raise ValueError("verilog_files must not be empty")
    if clock_period <= 0:
        raise ValueError("clock_period must be > 0")

    return {
        "DESIGN_NAME": design_name,
        "VERILOG_FILES": list(verilog_files),
        "CLOCK_PORT": clock_port,
        "CLOCK_PERIOD": float(clock_period),
        "PDK": pdk,
        "DIE_AREA": list(die_area),
    }


def write_config(
    config: dict,
    dest: Path | str,
) -> Path:
    """Write *config* dict to *dest* as JSON.

    Args:
        config: Config dict produced by :func:`build_config`.
        dest:   Destination file path (typically ``<run_dir>/config.json``).

    Returns:
        Resolved :class:`~pathlib.Path` of the written file.
    """
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(config, indent=2))
    return dest.resolve()
