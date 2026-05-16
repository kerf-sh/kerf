"""
kerf_cad_core.cuttingtool — cutting-tool geometry, mechanics & tool-life economics.

Public API (re-exported for convenience):

    from kerf_cad_core.cuttingtool import (
        orthogonal_to_normal,
        normal_to_orthogonal,
        merchant_orthogonal,
        specific_cutting_energy,
        cutting_power,
        taylor_tool_life,
        taylor_extended_tool_life,
        economic_cutting_speed,
        max_production_rate_speed,
        break_even_speed,
        machinability_rating,
        nose_radius_roughness,
    )

Distinct from:
  cncfeeds/  — machine-level cutting parameters (feeds, speeds table)
  turning/   — lathe canned cycles & G-code post-processor
  gcode/     — raw G-code generation

References
----------
Boothroyd, G. & Knight, W.A. "Fundamentals of Machining and Machine Tools",
  3rd ed. (2006)
Shaw, M.C. "Metal Cutting Principles", 2nd ed. (2005)
Merchant, M.E. (1945) J. Appl. Phys. 16, 267–275
Taylor, F.W. (1907) Trans. ASME 28, 31–350
Cook, N.H. (1973) CIRP Ann. 22, 45–48

Author: imranparuk
"""

from kerf_cad_core.cuttingtool.tool import (
    orthogonal_to_normal,
    normal_to_orthogonal,
    merchant_orthogonal,
    specific_cutting_energy,
    cutting_power,
    taylor_tool_life,
    taylor_extended_tool_life,
    economic_cutting_speed,
    max_production_rate_speed,
    break_even_speed,
    machinability_rating,
    nose_radius_roughness,
)

__all__ = [
    "orthogonal_to_normal",
    "normal_to_orthogonal",
    "merchant_orthogonal",
    "specific_cutting_energy",
    "cutting_power",
    "taylor_tool_life",
    "taylor_extended_tool_life",
    "economic_cutting_speed",
    "max_production_rate_speed",
    "break_even_speed",
    "machinability_rating",
    "nose_radius_roughness",
]
