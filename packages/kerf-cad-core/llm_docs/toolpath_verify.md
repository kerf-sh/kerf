# Toolpath Verification — `procsim/toolpath_verify.py`

Voxel-based G-code simulation for NC toolpath verification: material removal,
collision/gouge detection, remaining stock map, MRR. Pure Python; no NumPy.

---

## Physical model

**Voxel model only.** Cubic voxel grid representing the stock block. Each feed
or rapid move sweeps the tool through the grid, removing occupied voxels. The
tool is swept as a cylinder (flat/ball/bull styles affect which voxels are marked
inside the cutter envelope). The holder above the flute length is checked
separately for collisions.

All coordinates are in the stock's native units (typically mm). +Z is up;
the spindle moves in −Z to cut.

---

## Supported-input contract

- G-code parser supports: G00 / G01 linear moves, G02 / G03 circular arcs
  (in G17 plane), G81–G83 canned drill cycles, M03/M05 spindle, T/M06 tool
  changes. Other codes are silently skipped with a warning.
- Stock must be a rectangular box built by `make_stock`.
- Tool styles: `"flat"`, `"ball"`, `"bull"` (bull-nose radius = `diameter/4`).
- `part_envelope` is optional; if provided, any material removal below
  `part_envelope["zmin"]` is flagged as a gouge.

---

## Public API

### `make_stock(xmin, xmax, ymin, ymax, zmin, zmax, voxel_size=1.0) → dict`

Build a fully-occupied voxel stock grid.

Returns:
```json
{
  "ok": true,
  "xmin": 0, "xmax": 100, ...,
  "voxel_size": 0.5,
  "nx": 200, "ny": 160, "nz": 60,
  "voxels": "<bytearray, 1=occupied>"
}
```

### `make_tool(style="flat", diameter=10.0, flute_length=25.0, holder_diameter=None, holder_length=50.0) → dict`

Build a tool description dict.

`style`: `"flat"` | `"ball"` | `"bull"`.
`holder_diameter`: defaults to `diameter * 1.2` if not supplied.

Returns `{"ok": True, "style", "diameter", "flute_length", "holder_diameter", "holder_length"}`.

### `simulate(gcode, stock, tool, part_envelope=None, voxel_size=None) → dict`

Parse and simulate a G-code program against the stock.

- `gcode`: raw G-code string.
- `stock`: dict from `make_stock()` — **mutated in-place** (voxels removed).
- `tool`: dict from `make_tool()`.
- `part_envelope`: optional `{"zmin": float}` gouge-detection floor.

Returns:
```json
{
  "ok": true,
  "violations": [
    {
      "type": "rapid_collision|gouge|holder_collision",
      "move_index": 12,
      "x": 45.0, "y": 20.0, "z": 5.0,
      "line_no": 142,
      "detail": "G00 rapid into occupied stock"
    }
  ],
  "air_cut_pct": 3.2,
  "voxels_removed": 18420,
  "voxels_initial": 24000,
  "voxels_remaining": 5580,
  "volume_removed_units3": 2302.5,
  "mrr_nominal_cm3_min": 48.0,
  "mrr_achieved_cm3_min": 46.5,
  "segments_processed": 1840,
  "overcut_voxels": 0,
  "undercut_voxels": 12,
  "warnings": ["T02 tool change at line 20"]
}
```

Never raises; returns `{"ok": False, "reason": "..."}` on bad input.

---

## Usage

```python
from kerf_cad_core.procsim.toolpath_verify import make_stock, make_tool, simulate

# 100×80×30 mm stock, 0.5 mm voxels
stock = make_stock(0, 100, 0, 80, 0, 30, voxel_size=0.5)
tool  = make_tool("flat", diameter=10.0, flute_length=25.0)

with open("program.nc") as f:
    gcode = f.read()

result = simulate(gcode, stock, tool, part_envelope={"zmin": 0.0})

if result["violations"]:
    for v in result["violations"]:
        print(f"{v['type']} at move {v['move_index']} line {v['line_no']}")
        print(f"  {v['detail']}")

print(f"material removed: {result['volume_removed_units3']:.0f} mm³")
print(f"air-cut: {result['air_cut_pct']:.1f}%")
```

---

## Notes

- `stock` is mutated in-place. To compare before/after, copy `stock["voxels"]`
  before calling `simulate`.
- `voxel_size` in `simulate` is accepted but ignored — the stock's pre-built
  grid is used as-is.
- Memory: `nx × ny × nz` bytes. For 100×80×30 mm at 0.5 mm voxels: 200×160×60
  = 1.92 M voxels = ~2 MB.
- Holder collision detection uses a cylinder of `holder_diameter` × `holder_length`
  above the flute. Narrow `holder_diameter` or shorter `holder_length` to reduce
  false positives on deep pockets.
- `air_cut_pct` > ~20% often indicates inefficient toolpath; check for excessive
  Z-clearance moves.

## References

- Zhu, W.H. & Kapoor, S.G. (1994). "Dexel-based NC verification." *Int. J. Adv.
  Manuf. Technol.* 9(2).
- Sullivan, A., Resnick, D. & Klug, M. (2000). "Material removal simulation."
  *CIRP Annals* 49(1).
