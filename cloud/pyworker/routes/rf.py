"""
RF S-parameter analysis via scikit-rf.

POST /run-rf-study
Body: {
    "project_id": str,
    "rf_study_file_id": str,
    "touchstone_b64": str,
    "port_impedance": float (default 50.0),
    "freq_unit": str (default "GHz")
}

Algorithm:

1. Decode the base64-encoded touchstone data.
2. Load as skrf.Network object.
3. Renormalize to specified port_impedance if different from touchstone Z0.
4. Compute VSWR from S11: VSWR = (1 + |S11|) / (1 - |S11|)
5. Compute Return Loss in dB: RL = -20 * log10(|S11|)
6. Compute Insertion Loss in dB: IL = -20 * log10(|S21|) for 2-port
7. Generate Smith chart SVG via matplotlib rendering.
8. Return result JSON to be stored in rf_jobs table.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import base64
import tempfile
import os

router = APIRouter()


class RFStudyRequest(BaseModel):
    project_id: str
    rf_study_file_id: str
    touchstone_b64: str = ""
    port_impedance: float = Field(default=50.0, gt=0)
    freq_unit: str = Field(default="GHz")


def vswr_from_s11(s11_mag):
    """Compute VSWR from |S11| magnitude."""
    return [(1.0 + abs(s)) / (1.0 - abs(s)) if abs(s) < 1.0 else float('inf') for s in s11_mag]


def return_loss_db(s11_mag):
    """Compute return loss in dB from |S11| magnitude."""
    return [-20.0 * _log10(abs(s)) if abs(s) > 0 else float('inf') for s in s11_mag]


def insertion_loss_db(s21_mag):
    """Compute insertion loss in dB from |S21| magnitude."""
    return [-20.0 * _log10(abs(s)) if abs(s) > 0 else float('inf') for s in s21_mag]


def _log10(x):
    import math
    if x <= 0:
        return 0.0
    return math.log10(x)


def generate_smith_chart_svg(freq, s11_data, port_z0=50.0, freq_unit="GHz"):
    """Generate Smith chart SVG for S11 data using matplotlib."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np

    fig, ax = plt.subplots(1, 1, figsize=(6, 6), dpi=120)
    ax.set_aspect('equal')

    ax.set_xlim(-1.1, 1.1)
    ax.set_ylim(-1.1, 1.1)
    ax.axis('off')

    real_vals = np.linspace(0, 1, 11)
    for r in real_vals:
        if r == 0:
            circle = plt.Circle((0, 0), 1.0, fill=False, color='gray', linewidth=0.5, alpha=0.5)
        else:
            center = r / (1 + r)
            radius = 1.0 / (1 + r)
            circle = plt.Circle((center, 0), radius, fill=False, color='gray', linewidth=0.5, alpha=0.5)
        ax.add_patch(circle)

    imag_vals = np.linspace(-1, 1, 21)
    for x in imag_vals:
        if x == 0:
            ax.axvline(x=1, color='gray', linewidth=0.5, alpha=0.5)
        else:
            r = 1.0 / abs(x)
            center = 0.5 * (1 + x / abs(x))
            radius = r / 2.0
            arc_x = center - radius if x < 0 else center + radius
            arc = plt.Circle((arc_x, 0.5 if x > 0 else -0.5), radius,
                           fill=False, color='gray', linewidth=0.5, alpha=0.5)
            ax.add_patch(arc)

    ax.axhline(y=0, color='gray', linewidth=0.5, alpha=0.3)
    ax.axvline(x=0, color='gray', linewidth=0.5, alpha=0.3)

    if len(freq) > 0 and len(s11_data) == len(freq):
        s11_complex = [complex(s.get('re', 0), s.get('im', 0)) if isinstance(s, dict) else s
                      for s in s11_data]

        marker_count = min(len(freq), 20)
        step = max(1, len(freq) // marker_count)
        indices = list(range(0, len(freq), step))

        cmap = plt.cm.viridis
        for i, idx in enumerate(indices):
            z = s11_complex[idx]
            if z != 0:
                gamma = z / port_z0 if isinstance(z, (int, float)) else z
            else:
                gamma = 0
            x_pos = gamma.real if hasattr(gamma, 'real') else gamma
            y_pos = gamma.imag if hasattr(gamma, 'imag') else 0
            color = cmap(i / len(indices))
            ax.plot(x_pos, y_pos, 'o', markersize=4, color=color, zorder=5)

        s11_x = [s.real if hasattr(s, 'real') else 0 for s in s11_complex]
        s11_y = [s.imag if hasattr(s, 'imag') else 0 for s in s11_complex]
        ax.plot(s11_x, s11_y, '-', color='#22d3ee', linewidth=1.0, alpha=0.7, zorder=4)

    ax.set_title(f"S11 Smith Chart ({freq_unit})", fontsize=10, pad=8)

    tmp = tempfile.NamedTemporaryFile(suffix='.svg', delete=False)
    tmp.close()
    try:
        plt.savefig(tmp.name, format='svg', bbox_inches='tight', transparent=True)
        with open(tmp.name, 'r', encoding='utf-8') as f:
            svg_content = f.read()
    finally:
        os.unlink(tmp.name)
    plt.close(fig)

    return svg_content


@router.post("/run-rf-study")
async def run_rf_study(req: RFStudyRequest):
    """
    Run S-parameter analysis on a .rf-study file.
    """
    try:
        import skrf as rf
        import numpy as np
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except ImportError as e:
        return {
            "status": "error",
            "error": f"scikit-rf not available: {e}",
            "warnings": [],
            "errors": [str(e)],
        }

    if not req.touchstone_b64:
        return {
            "status": "error",
            "error": "touchstone_b64 required",
            "warnings": [],
            "errors": ["touchstone_b64 is required"],
        }

    try:
        with tempfile.NamedTemporaryFile(suffix='.s2p', delete=False) as tmp:
            tmp_path = tmp.name

        touchstone_data = base64.b64decode(req.touchstone_b64)
        with open(tmp_path, 'wb') as f:
            f.write(touchstone_data)

        network = rf.Network(tmp_path)
        os.unlink(tmp_path)

        if req.port_impedance != network.z0[0]:
            network.renormalize(req.port_impedance)

        freq = network.frequency
        freq_array = freq.to_freq_unit(req.freq_unit)

        s11 = network.s[:, 0, 0]
        s11_mag = np.abs(s11)
        vswr = vswr_from_s11(s11_mag.tolist())
        return_loss = return_loss_db(s11_mag.tolist())

        insertion_loss = []
        if network.number_of_ports >= 2:
            s21 = network.s[:, 1, 0]
            s21_mag = np.abs(s21)
            insertion_loss = insertion_loss_db(s21_mag.tolist())
        else:
            insertion_loss = [0.0] * len(freq_array)

        s11_list = []
        for s in s11:
            s11_list.append({"re": float(s.real), "im": float(s.imag)})

        smith_svg = generate_smith_chart_svg(
            freq_array.tolist(),
            s11_list,
            port_z0=req.port_impedance,
            freq_unit=req.freq_unit
        )

        return {
            "status": "done",
            "frequency_range": freq_array.tolist(),
            "frequency_unit": req.freq_unit,
            "port_impedance": req.port_impedance,
            "num_ports": network.number_of_ports,
            "num_points": len(freq_array),
            "vswr": vswr,
            "return_loss_db": return_loss,
            "insertion_loss_db": insertion_loss,
            "smith_chart_svg": smith_svg,
            "warnings": [],
            "errors": [],
        }

    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "warnings": [],
            "errors": [str(e)],
        }
