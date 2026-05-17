# IBIS Reader — `ibis_reader.py`

ANSI/EIA-656 IBIS (I/O Buffer Information Specification) file reader. Parses buffer models for SI simulation and package parasitic extraction.

---

## Standard

ANSI/EIA-656 IBIS versions 3.2–6.1. A plain-text line-format specification for I/O buffer electrical models, used by signal integrity tools (HyperLynx, SiSoft Quantum SI, Ansys SIwave).

---

## Public API

### `read_ibis(path_or_fileobj) → IBISFile`

Parse a `.ibs` file. Returns an `IBISFile` dataclass.

`IBISFile` fields:
```
header: IBISHeader
components: list[IBISComponent]
models: list[IBISModel]
```

### `IBISHeader`

```python
@dataclass
class IBISHeader:
    ibis_ver: str        # e.g. "6.1"
    file_name: str
    file_rev: str
    source: str
    notes: str
```

### `IBISComponent`

```python
@dataclass
class IBISComponent:
    name: str
    manufacturer: str
    package: PackageParasitics    # R_pkg, L_pkg, C_pkg
    pins: list[PinRecord]         # {pin_name, signal_name, model_name, R_pin, L_pin, C_pin}
```

### `IBISModel`

```python
@dataclass
class IBISModel:
    name: str
    model_type: str           # "Input", "Output", "I/O", "3-state", "Open_drain", etc.
    c_comp_pf: float          # Buffer input capacitance
    vinl_v: float             # Input low threshold
    vinh_v: float             # Input high threshold
    iv_data: dict             # {"pullup": [(V, I), ...], "pulldown": [(V, I), ...]}
    vt_data: dict             # {"rising": [(t, V), ...], "falling": [(t, V), ...]}
    ramp: dict | None         # {"dV/dt_r": ..., "dV/dt_f": ...}
    diff_model_ref: str | None
```

### `get_model(ibis_file, model_name) → IBISModel | None`

Look up a model by name; returns `None` if not found.

### `extract_vt_waveform(model, *, edge="rising", supply_v=3.3) → list[tuple[float, float]]`

Return the V(t) waveform for a given edge as `[(t_s, V), ...]`.

---

## Usage

```python
from kerf_imports.ibis_reader import read_ibis, get_model, extract_vt_waveform

ibis = read_ibis("my_device.ibs")
print(ibis.header.ibis_ver)

for comp in ibis.components:
    print(comp.name, comp.package)

model = get_model(ibis, "LVDS_OUT_100")
if model:
    print(model.model_type, model.c_comp_pf)
    waveform = extract_vt_waveform(model, edge="rising", supply_v=1.8)
```

---

## Notes

- Read-only: no write support.
- IBIS BIRD (Buffer Interface Reference Data) extensions and multi-lingual model containers (`.ams`) are not supported.
- `iv_data` and `vt_data` are parsed as raw tables; use `extract_vt_waveform` for a normalised waveform.
- `ramp` is populated from `[Ramp]` section if present; preferred over `[Rising Waveform]` for fast approximations.
- Differential models (`[Diff Pin]`) are cross-linked via `diff_model_ref`.
