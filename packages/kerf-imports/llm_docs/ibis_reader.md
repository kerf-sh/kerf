# IBIS Reader — `ibis_reader.py`

ANSI/EIA-656 IBIS (I/O Buffer Information Specification) file reader. Parses buffer models, package parasitics, pin tables, and V-I / V-t waveform data for SI simulation. Pure Python — stdlib only; IBIS is a line-oriented keyword text format.

---

## Standard

ANSI/EIA-656 IBIS versions 1.x–6.x. Used by HyperLynx, SiSoft Quantum SI, Ansys SIwave, and similar signal-integrity tools.

---

## Public entrypoint

### `parse_ibis(text: str | bytes) → dict`

Parse an IBIS `.ibs` file. Returns a plain dict — never raises.

**Supported IBIS keywords:**
- `[IBIS Ver]`, `[File Name]`, `[File Rev]`
- `[Component]`, `[Manufacturer]`
- `[Package]` — R_pkg / L_pkg / C_pkg with typ/min/max columns
- `[Pin]` — pin table: signal_name, model_name, R/L/C per pin
- `[Model]` — Model_type, C_comp, Vinl, Vinh, Vmeas
- `[Voltage Range]`, `[Temperature Range]`
- `[Pullup]`, `[Pulldown]`, `[GND_clamp]`, `[POWER_clamp]` — V-I tables
- `[Ramp]` — dV/dt_r and dV/dt_f

Unsupported keywords collected in `warnings`; never raise.

**Return schema (success):**
```json
{
  "ok": true,
  "ibis_version": "6.1",
  "file_name": "my_device.ibs",
  "file_rev": "1.0",
  "components": [
    {
      "name": "MY_IC",
      "manufacturer": "ACME Corp",
      "package": {
        "R_pkg": {"typ": 0.1, "min": 0.08, "max": 0.12},
        "L_pkg": {"typ": 2.5e-9, "min": 2.0e-9, "max": 3.0e-9},
        "C_pkg": {"typ": 1.5e-12, "min": 1.2e-12, "max": 1.8e-12}
      },
      "pins": [
        {
          "name": "A0",
          "signal_name": "DATA0",
          "model_name": "LVCMOS18_OUT",
          "R_pin": null,
          "L_pin": null,
          "C_pin": null
        }
      ]
    }
  ],
  "models": {
    "LVCMOS18_OUT": {
      "name": "LVCMOS18_OUT",
      "model_type": "Output",
      "c_comp": {"typ": 2.5e-12, "min": null, "max": null},
      "vinl": 0.45,
      "vinh": 1.35,
      "vmeas": 0.9,
      "voltage_range": {"typ": 1.8, "min": 1.7, "max": 1.9},
      "pulldown": [{"V": 0.0, "typ": 0.0, "min": null, "max": null}, ...],
      "pullup": [...],
      "gnd_clamp": [...],
      "power_clamp": [...],
      "ramp": {
        "dV_dt_r": {"typ": "1.2V/1ns", "min": null, "max": null},
        "dV_dt_f": {"typ": "1.1V/1.1ns", "min": null, "max": null}
      },
      "temperature_range": {"typ": 25.0, "min": 0.0, "max": 85.0}
    }
  },
  "warnings": []
}
```

**Return schema (error):**
```json
{"ok": false, "reason": "..."}
```

---

## Usage

```python
from kerf_imports.ibis_reader import parse_ibis

with open("my_device.ibs") as f:
    text = f.read()

result = parse_ibis(text)
if not result["ok"]:
    print("Parse error:", result["reason"])
else:
    print("IBIS version:", result["ibis_version"])

    for comp in result["components"]:
        print(comp["name"], comp["manufacturer"])
        print("L_pkg typ:", comp["package"]["L_pkg"]["typ"])
        for pin in comp["pins"]:
            print(f"  {pin['name']} → model {pin['model_name']}")

    # Access a model's V-I data
    model = result["models"].get("LVCMOS18_OUT")
    if model:
        print("Model type:", model["model_type"])
        print("C_comp typ:", model["c_comp"]["typ"])
        for row in model["pulldown"][:3]:
            print(f"  V={row['V']:.3f}, I_typ={row['typ']}")
```

---

## LLM tool

**`import_ibis`** — registered via `@register`; gated on `"imports.ibis"` capability.

Accepts `file_id` pointing to an `.ibs` file already uploaded to the project. Returns the same dict schema as `parse_ibis`.

---

## Notes

- Read-only: no write support.
- V-I and V-t tables are returned as raw rows with typ/min/max columns. The `ramp` section `dV_dt_r`/`dV_dt_f` values are stored as raw strings (e.g. `"1.2V/1ns"`) because the IBIS spec allows flexible formatting.
- IBIS BIRD (Buffer Interface Reference Data) extensions and multi-lingual model containers (`.ams`) are not supported.
- `[Rising Waveform]` / `[Falling Waveform]` V-t table sections are not currently parsed (only `[Ramp]` is extracted). If you need full waveform data, use an IBIS-AMI capable tool.
- Differential models referenced by `[Diff Pin]` sections are not cross-linked in the output; both halves are returned as independent models.

---

## Standard citation

ANSI/EIA-656 — I/O Buffer Information Specification (IBIS), revision 6.1 (IBIS Open Forum, 2019).
