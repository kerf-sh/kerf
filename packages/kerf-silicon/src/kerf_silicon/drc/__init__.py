"""
kerf_silicon.drc — Design Rule Check engine.

Quick-start
-----------
    from kerf_silicon.drc import check
    from kerf_silicon.drc.rules import SKY130_RULES

    layout = [
        {"layer": "met1", "polygon": [(0, 0), (500, 0), (500, 500), (0, 500)]},
    ]
    report = check(layout, SKY130_RULES)
    print(report.to_dict())
"""

from .engine import DrcReport, Violation, check

__all__ = ["check", "DrcReport", "Violation"]
