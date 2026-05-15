# Footprint / Symbol Library Management

Two LLM tools manage symbol↔footprint assignments for a design and validate
that every component is ready for PCB layout.

---

## `assign_footprint`

Assigns footprints to schematic symbols in a design's component list and
manages the logical library table (lib_name → source path).

**When to use:** The user asks to assign footprints, link symbols to pads,
set up the footprint library table, or auto-suggest footprints for
unassigned components.  Always follow with `check_library_assignments` to
confirm the design is valid before handing off to layout.

**Input:**

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `components` | array | yes | List of component dicts (see shape below) |
| `assignments` | object | yes | `{refdes: "LibName:EntryName"}` map; `{}` to skip |
| `lib_table` | object | no | Logical lib name → source path; `{}` if none yet |
| `auto_suggest` | boolean | no | Attempt name-match suggestions for unassigned components (default `false`) |

**Component dict shape** (same as `kerf_imports.kicad_library` output):

```json
{
  "refdes":           "R1",
  "name":             "10k",
  "schematic_symbol": {
    "library":     "Device",
    "entry_name":  "R",
    "pin_count":   2,
    "pins":        [{"name": "~", "number": "1", "electrical_type": "passive"}, …]
  },
  "pcb_footprint": null
}
```

**Output:**

| Field | Type | Notes |
|-------|------|-------|
| `updated` | array[string] | Refdes that received a new footprint assignment |
| `suggested` | object | `{refdes: "Lib:Entry"}` auto-suggestions (not applied) |
| `not_found` | array[string] | Refdes in `assignments` not present in components |
| `lib_table` | object | The (possibly unchanged) library table |
| `components` | array | Updated component list with footprints applied |
| `message` | string | Human-readable summary |

**Example:**

```json
{
  "components": [
    {"refdes": "R1", "schematic_symbol": {"pin_count": 2, …}, "pcb_footprint": null},
    {"refdes": "U1", "schematic_symbol": {"pin_count": 8, …}, "pcb_footprint": null}
  ],
  "assignments": {
    "R1": "Resistor_SMD:R_0402",
    "U1": "Package_DIP:DIP-8_W7.62mm"
  },
  "lib_table": {
    "Resistor_SMD": "/usr/share/kicad/footprints/Resistor_SMD.pretty"
  }
}
```

---

## `check_library_assignments`

Validates footprint assignments for every component in a design.

**When to use:** After `assign_footprint`, or whenever the user asks to check
whether all components are ready for layout, verify pin/pad counts, or audit
reference designators.

**Input:**

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `components` | array | yes | List of component dicts (same shape as above) |
| `lib_table` | object | no | Optional library table — included in the report |

Components may carry a lightweight `footprint_ref` string
(`"LibName:EntryName"`) instead of a full `pcb_footprint` object; the tool
accepts both.

**Output:**

```json
{
  "status":  "OK" | "ISSUES_FOUND",
  "total":   5,
  "issues": [
    {
      "kind":     "pin_pad_mismatch",
      "severity": "error",
      "refdes":   "R1",
      "message":  "Component \"R1\": symbol \"Device:R\" has 2 pin(s) but footprint \"Resistor_SMD:R_0805\" declares 4 pad(s)."
    }
  ],
  "summary": {
    "missing_footprint":     0,
    "pin_pad_mismatch":      1,
    "missing_refdes":        0,
    "duplicate_refdes":      0,
    "invalid_refdes_format": 0
  },
  "lib_table": { … },
  "message":   "Assignment check: 1 issue(s) found in 5 component(s). 1 pin/pad mismatch(es)."
}
```

### Issue kinds

| Kind | Severity | Meaning |
|------|----------|---------|
| `missing_footprint` | error | Component has neither `pcb_footprint` nor `footprint_ref` |
| `pin_pad_mismatch` | error | Symbol `pin_count` ≠ footprint `pad_count` |
| `missing_refdes` | error | Component has a blank or absent `refdes` field |
| `duplicate_refdes` | error | Two components share the same reference designator |
| `invalid_refdes_format` | warning | Refdes does not match `[letters][digits]` pattern (e.g. `R1`, `U3`) |

### Pin/pad mismatch

The check compares:
- `schematic_symbol.pin_count` (or `len(schematic_symbol.pins)`)
- `pcb_footprint.pad_count` (or `len(pcb_footprint.pads)`)

The check is **skipped** when either side has no count information
(e.g. a lightweight `footprint_ref` string with no `pad_count`).

### Clean design

A design is ready for layout when `status == "OK"`:

```json
{
  "status":  "OK",
  "total":   4,
  "issues":  [],
  "summary": {"missing_footprint": 0, "pin_pad_mismatch": 0, …},
  "message": "Assignment check passed: 4 component(s), all footprints assigned and pin/pad counts match."
}
```

---

## Typical workflow

```
1. Import KiCad library  →  kerf_imports / import-kicad-library
2. Assign footprints     →  assign_footprint
3. Validate              →  check_library_assignments
4. If ISSUES_FOUND: fix assignments and re-run step 3
5. Hand off to layout    →  ERC, copper pour, routing, …
```
