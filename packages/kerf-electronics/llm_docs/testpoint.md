# Testpoint Auto-placement and Bed-of-nails Fixture

Two LLM tools generate an ICT (in-circuit test) probe plan and bed-of-nails
fixture report from a CircuitJSON board.

No new copper is added to the board.  The tools select optimal probe points
from **existing pads and vias** in the CircuitJSON, then produce a fixture
deliverable (probe list + drill CSV) ready for submission to a fixture shop.

---

## `generate_testpoints`

Auto-places one probe point per net for ICT / bed-of-nails fixture planning.

**When to use:** User asks to plan testpoints, generate an ICT probe list,
identify which nets are accessible for bed-of-nails testing, or check fixture
coverage before handing off to a fixture vendor.

**Input:**
- `circuit_json` (required) — parsed CircuitJSON array from the active board.
- `access_side` (optional) — `"top"` (default) or `"bottom"`. The physical side
  the fixture accesses. Through-hole pads and vias are accessible from either side.
- `min_spacing_mm` (optional) — minimum centre-to-centre probe spacing in mm.
  Default `2.54` (100-mil standard ICT grid). Use `1.27` for 50-mil fixtures.

**Output:**
- `probe_count` — probes successfully placed.
- `net_count` — total named nets (N/C excluded).
- `unreachable_count` — nets with no accessible probe point.
- `coverage_pct` — `probe_count / net_count × 100`.
- `probes[]` — probe list (see fields below).
- `unreachable_nets[]` — `{net, reason}` for unplaceable nets.
- `message` — human-readable summary.

### Probe selection priority

For each net, candidates are ranked:

| Tier | Pad type                        | Notes                                    |
|------|---------------------------------|------------------------------------------|
| 0    | Via (layer 00 = both sides)     | Preferred — clear of component bodies    |
| 1    | PTH pad (drilled + plated)      | Accessible from both sides               |
| 2    | SMT pad on `access_side`        | Standard surface probe                   |
| 3    | SMT pad on opposite side        | Fallback — possible but less preferred   |

Within each tier, the pad with the largest footprint wins (easier probe registration).

### Grid snapping and spacing

Each candidate's position is snapped to the nearest `min_spacing_mm` grid point.
If the snapped position is within `min_spacing_mm` of any already-placed probe,
the next candidate for that net is tried.  If all candidates conflict, the net is
added to `unreachable_nets` with `reason: "spacing_conflict"`.

### Probe fields

| Field          | Description                                              |
|----------------|----------------------------------------------------------|
| `net`          | Net name                                                 |
| `x_mm`         | Pad centre X (mm, from CircuitJSON)                      |
| `y_mm`         | Pad centre Y (mm, from CircuitJSON)                      |
| `snapped_x_mm` | X snapped to probe grid                                  |
| `snapped_y_mm` | Y snapped to probe grid                                  |
| `side`         | `"top"` or `"bottom"` — which side the probe contacts    |
| `pad_type`     | `"via"`, `"pth"`, or `"smt"`                             |
| `probe_dia_mm` | Probe tip diameter (mm), derived from pad size           |
| `refdes`       | Component reference designator (blank for vias)          |
| `pin`          | Pin number (blank for vias)                              |

### Unreachable reasons

| Reason             | Meaning                                                  |
|--------------------|----------------------------------------------------------|
| `no_pads`          | Net exists in CircuitJSON but has no pad/via elements    |
| `spacing_conflict` | All candidate pads collide with already-placed probes    |

---

## `fixture_report`

Generates a complete bed-of-nails ICT fixture report, including coverage % and
a drill/probe CSV for fixture shop submission.

**When to use:** User wants the full fixture deliverable — coverage metric,
probe CSV, summary text — for handoff to a contract test fixture vendor or for
ICT planning documentation.

**Input:** same as `generate_testpoints`, plus:
- `stem` (optional) — board name for the report header and CSV filename (default `"board"`).

**Output:**
- Everything from `generate_testpoints`, plus:
- `drill_csv` — CSV text (see columns below). Save as `<stem>-fixture-probes.csv`.
- `csv_filename` — suggested filename (`<stem>-fixture-probes.csv`).
- `summary` — human-readable text block suitable for a test plan document.

### Drill/probe CSV columns

| Column        | Content                                                  |
|---------------|----------------------------------------------------------|
| `Net`         | Net name                                                 |
| `X_mm`        | Probe X (grid-snapped, mm)                               |
| `Y_mm`        | Probe Y (grid-snapped, mm)                               |
| `Side`        | `top` or `bottom`                                        |
| `Probe_dia_mm`| Probe tip diameter (mm)                                  |
| `Pad_type`    | `via`, `pth`, or `smt`                                   |
| `Refdes`      | Component reference (blank for vias)                     |
| `Pin`         | Pin number (blank for vias)                              |

---

## Probe diameter derivation

Probe tip size is chosen from the pad geometry to maximise contact reliability:

```
probe_dia_mm = clamp(min(pad_width, pad_height) / 2,  min=0.5 mm,  max=2.5 mm)
```

This follows common ICT fixture practice (IPC-9252 guidance):
- Very small pads (< 1 mm) get a 0.5 mm probe.
- Large pads / PTH lands can accept up to a 2.5 mm probe.

---

## Coverage metric

```
coverage_pct = placed_probes / total_named_nets × 100
```

`total_named_nets` excludes pads assigned `N/C` (no net).  A coverage of 100 %
means every named net has at least one reachable probe point at the chosen pitch.
Nets in `unreachable_nets` reduce coverage; the reason explains whether the cause
is a genuine layout gap (`no_pads`) or a pitch constraint (`spacing_conflict`).

---

## Typical workflow

1. Run `netlist_report` (from `kerf_electronics.tools.ipc_netlist`) to confirm
   connectivity before planning probes.
2. Call `generate_testpoints` for a quick coverage check.
3. If coverage is < 100 %, inspect `unreachable_nets` — for `spacing_conflict`
   nets, try a tighter `min_spacing_mm` (e.g. 1.27 mm); for `no_pads` nets,
   add a testpoint via or pad in the schematic.
4. Call `fixture_report` to generate the final drill CSV for the fixture vendor.
