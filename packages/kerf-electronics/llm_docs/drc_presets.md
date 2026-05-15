# DRC Manufacturing Constraint Presets

Named preset profiles for PCB Design Rule Check (DRC). Each preset encodes the
minimum trace, clearance, drill and copper-to-edge values for a recognised
standard or representative fab capability. Pass the preset name to
`run_drc_with_preset` to validate a board against that profile in one step.

---

## Tools

| Tool | Description |
|---|---|
| `list_drc_presets` | Returns the full catalogue: name, description, source, constraint values. |
| `run_drc_with_preset` | Runs DRC through the existing `pcb_drc` engine using a named preset's constraints; returns `errors`, `warnings`, `violations_by_rule`, and `summary`. |

---

## IPC-2221B Producibility Classes

IPC-2221B *"Generic Standard on Printed Board Design"* (2003, reaffirmed 2012)
defines three producibility levels in Table 6-2 (formerly called "complexity
levels A/B/C"). They describe what a board *requires of the fabricator*, not
the component/assembly process class of IPC-610.

| Rule | Class 1 (Level A) | Class 2 (Level B) | Class 3 (Level C) |
|---|---|---|---|
| `min_trace_width_mm` | 0.25 | 0.15 | 0.075 |
| `min_via_clearance_mm` | 0.25 | 0.15 | 0.075 |
| `min_drill_spacing_mm` | 0.80 | 0.50 | 0.25 |
| `min_copper_to_edge_mm` | 0.50 | 0.30 | 0.20 |

**Source:** IPC-2221B:2003, Section 4.3, Table 6-2 (producibility levels A/B/C).

### When to use each class

- **Class 1 (ipc_2221_class_1)** — Consumer / hobby / non-critical boards.
  Widest tolerances; lower fabrication cost; suitable where reliability
  requirements are minimal.

- **Class 2 (ipc_2221_class_2)** — General industrial / commercial electronics.
  The most common class for production PCBs. Covers the majority of
  cost-effective fabrication processes.

- **Class 3 (ipc_2221_class_3)** — High-reliability, defence, medical,
  aerospace. Tightest geometric tolerances; demands tightly controlled
  fabrication processes; typically higher cost.

---

## Representative Fab-House Profiles

These profiles are **not specific to any vendor's proprietary specification**.
Values are derived from publicly available capability guides and are included
as a convenience reference for early-stage design rule checking.

| Rule | `prototype_standard` | `prototype_advanced` |
|---|---|---|
| `min_trace_width_mm` | 0.152 (~6 mil) | 0.100 (~4 mil) |
| `min_via_clearance_mm` | 0.152 (~6 mil) | 0.100 |
| `min_drill_spacing_mm` | 0.40 | 0.25 |
| `min_copper_to_edge_mm` | 0.30 | 0.20 |

### prototype_standard

Representative capability of common 2-layer quick-turn prototype services
(e.g. "6/6 mil" trace/space process). Drill at 0.4 mm minimum. Suitable for
through-hole and standard SMD boards. Copper-to-edge 0.30 mm.

### prototype_advanced

Representative capability of advanced 4-layer prototype services with
laser-drilled microvias (~0.25 mm), 4/4 mil trace/space. Suitable for
high-density SMD and BGA-breakout designs.

---

## Constraint Merging Behaviour

When `run_drc_with_preset` is called, the preset values are merged with any
`drc_rules` already set on the `pcb_board` element:

- If a rule is **absent** from the board, the preset value is used.
- If a rule is **already set** on the board, the **less restrictive** (lower)
  of the board value and the preset value is used as the effective minimum.

This means a board can *relax* a preset constraint (e.g. a board that
explicitly sets `min_trace_width_mm: 0.10` while running under Class 2 will
use 0.10 mm, not 0.15 mm). The preset acts as a **default floor**, not an
inviolable maximum.

If you need the preset to act as an absolute minimum regardless of board
overrides, use `set_drc_rule` to stamp the preset values onto the board before
running `run_pcb_drc`.

---

## Example Usage

```python
# List all available presets
await run_tool("list_drc_presets", {})

# Validate a board against IPC Class 2
report = await run_tool("run_drc_with_preset", {
    "circuit_json": circuit,
    "preset_name": "ipc_2221_class_2",
})
print(report["summary"])
# {"error_count": 3, "warning_count": 1, "total_violations": 4,
#  "applied_constraints": {"min_trace_width_mm": 0.15, ...}}

# Violations grouped by rule kind
for kind, viols in report["violations_by_rule"].items():
    print(f"{kind}: {len(viols)} violation(s)")
```

---

## IPC References

- IPC-2221B: *Generic Standard on Printed Board Design*, IPC, 2003.
  Sections 4.3, 6.4; Table 6-2 (producibility levels).
- IPC-2221A: previous revision (2003); superseded by IPC-2221B.
- The three producibility levels (A/B/C) in IPC-2221 are distinct from the
  three *performance classes* (1/2/3) in IPC-6012 (qualification and
  performance specification for rigid printed boards). Kerf's preset names
  use "class_1/2/3" to align with common industry shorthand for the
  producibility levels.
