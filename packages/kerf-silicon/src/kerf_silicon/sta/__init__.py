"""kerf_silicon.sta — Static Timing Analysis (STA) pass.

Quick start::

    from kerf_silicon.liberty import parse as parse_liberty
    from kerf_silicon.sta import analyze, parse_sdc

    lib = parse_liberty(liberty_text)
    constraints = parse_sdc(sdc_text)
    report = analyze(netlist, lib, constraints)
    for path in report.worst_paths[:10]:
        print(path)

The STA pass is single-corner, single-clock, no on-chip variation.
"""
from kerf_silicon.sta.analyze import analyze, STAReport, PathReport
from kerf_silicon.sta.graph import TimingGraph, TimingNode, TimingEdge
from kerf_silicon.sta.sdc_reader import (
    parse_sdc,
    SDCConstraints,
    ClockDef,
    InputDelay,
    OutputDelay,
    MaxDelay,
    FalsePath,
)

__all__ = [
    "analyze",
    "STAReport",
    "PathReport",
    "TimingGraph",
    "TimingNode",
    "TimingEdge",
    "parse_sdc",
    "SDCConstraints",
    "ClockDef",
    "InputDelay",
    "OutputDelay",
    "MaxDelay",
    "FalsePath",
]
