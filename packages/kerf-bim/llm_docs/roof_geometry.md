# Roof Geometry — LLM Reference

Generate parametric B-rep roof geometry for BIM models.

## Roof Types

| type | faces | description |
|------|-------|-------------|
| `gable` | 4 | Two sloped faces + two vertical gable triangles |
| `hip` | 4 | Four sloped faces (triangular ends, trapezoidal sides) |
| `shed` | 1 | Single sloped face (lean-to) |
| `mono` | 1 | Alias for `shed` |

## Tool: `bim_make_roof`

Generate a B-rep Body for a parametric roof.

```json
{
  "roof_type": "gable",
  "x_min": 0,
  "y_min": 0,
  "x_max": 12000,
  "y_max": 8000,
  "base_z": 3000,
  "pitch_deg": 30,
  "overhang": 600,
  "material": "roof_tile"
}
```

Returns:

```json
{
  "ok": true,
  "roof_type": "gable",
  "faces_count": 4,
  "ridge_z_mm": 5309.4,
  "ridge_pts": [[...], [...]],
  "ifc_dict": {"type": "IfcRoof", "predefined_type": "GABLE_ROOF", ...}
}
```

### Key parameters

- `pitch_deg` — roof pitch angle in degrees [1, 89]. Default 30°.
- `overhang` — horizontal overhang beyond the wall plate on all sides (mm). Default 600.
- `base_z` — elevation of the top of the wall plate (mm).
- All dimensions in **mm**.

### IFC mapping

- `hip` → `IfcRoofTypeEnum.HIP_ROOF`
- `gable` → `IfcRoofTypeEnum.GABLE_ROOF`
- `shed` / `mono` → `IfcRoofTypeEnum.SHED_ROOF`

Reference: ISO 16739-1:2018 (IFC4) — IfcRoof.
