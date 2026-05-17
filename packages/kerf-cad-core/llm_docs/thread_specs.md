# Thread Specifications (`thread_specs.py`)

ISO metric (coarse + fine) and Unified (UNC/UNF) thread specification
catalog with computed tap-drill diameters; lookup by designation string.

---

## When to use

Reach for this module when the user asks about:

- tap-drill size for a given metric or imperial thread (M6, 1/4-20 UNC, etc.)
- minor diameter, pitch, or nominal major diameter for a thread designation
- listing all available UNC or UNF designations
- converting between inch and metric thread dimensions

---

## Public API

### `lookup(designation: str) -> ThreadSpec | None`

Return the spec dict for an exact designation, or `None` if not found
(case-sensitive, e.g. `"M6"`, `"1/4-20 UNC"`, `"#10-32 UNF"`).

```python
from kerf_cad_core.thread_specs import lookup

spec = lookup("M6")
# spec["major_dia_mm"]  → 6.0
# spec["pitch_mm"]      → 1.0
# spec["minor_dia_mm"]  → 4.773
# spec["tap_drill_mm"]  → 5.0
# spec["thread_class"]  → "6H/6g"
```

---

### `metric_coarse_designations() -> list[str]`

Return all ISO 261 coarse-series designations in ascending size order
(M1.6 through M64).

---

### `uts_unc_designations() -> list[str]`

Return all ASME B1.1 UNC designations (numbered #1 through #12 and
fractional 1/4 through 1-1/2).

---

### `uts_unf_designations() -> list[str]`

Return all ASME B1.1 UNF designations.

---

## Catalog contents

| Catalog | Dict | Coverage |
|---------|------|----------|
| `METRIC_COARSE` | `{designation: ThreadSpec}` | M1.6–M64 (ISO 261 coarse, 23 sizes) |
| `METRIC_FINE` | `{designation: ThreadSpec}` | M6x0.75–M48x2 (19 selected fine sizes) |
| `METRIC_ALL` | merged | all metric |
| `UTS_ALL` | `{designation: ThreadSpec}` | #0-80 UNF through 1-1/2 UNF/UNC |
| `ALL_THREADS` | merged | all above |

---

## `ThreadSpec` fields

| Field | Description |
|-------|-------------|
| `designation` | Canonical short form: `"M6"`, `"1/4-20 UNC"` |
| `standard` | `"ISO metric"` / `"UTS UNC"` / `"UTS UNF"` |
| `system` | `"metric"` / `"inch"` |
| `major_dia_mm` | Nominal major diameter (mm) |
| `pitch_mm` | Thread pitch (mm) |
| `minor_dia_mm` | Minor (root) diameter — ISO 68-1: d − 1.226869·P (metric); ASME B1.1: d − 1.299038/TPI (inch) |
| `tap_drill_mm` | Tap-drill diameter — ≈ major − pitch (75% engagement workshop approximation) |
| `major_dia_in` | Major diameter (inches, UTS only) |
| `pitch_in`, `minor_dia_in`, `tap_drill_in` | Inch equivalents (UTS only) |
| `thread_class` | `"6H/6g"` (metric) / `"2B/2A"` (UTS) |
| `series` | `"coarse"` / `"fine"` |

---

## Supported input contract

- Lookup is case-sensitive: `"M6"` works; `"m6"` returns `None`.
- Tap-drill formula is the common workshop 75%-engagement approximation
  (major − pitch), not the ISO 965-1 calculated value — suitable for
  standard through-holes, not tight-tolerance fits.
- Minor diameter formula: ISO 68-1 standard (60° thread geometry).
- Only the coarse and fine series listed in ISO 261 / ASME B1.1 are
  included; custom pitches are not in the catalog.

---

## Usage examples

**Tap-drill for M10 coarse:**

```python
from kerf_cad_core.thread_specs import lookup
s = lookup("M10")
print(s["tap_drill_mm"])   # 8.5
print(s["minor_dia_mm"])   # 8.160
```

**UNC fractional thread info:**

```python
s = lookup("1/2-13 UNC")
print(s["major_dia_in"])   # 0.5
print(s["tap_drill_mm"])   # 10.749
```

**List all metric coarse designations:**

```python
from kerf_cad_core.thread_specs import metric_coarse_designations
print(metric_coarse_designations())
# ['M1.6', 'M2', 'M2.5', ..., 'M64']
```

---

## References

ISO 261:2013 — ISO general purpose metric screw threads (series selection).
ISO 965-1:1998 — Metric thread tolerances; ISO 68-1 — Basic thread geometry (60°).
ASME B1.1-2003 — Unified Inch Screw Threads (UNC/UNF).
