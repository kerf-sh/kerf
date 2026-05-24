# Corridor B-rep and IFC Alignment — LLM Reference

Swept road corridor geometry: B-rep solid, volume estimate, and IFC export.

## Tool: `civil_corridor_brep`

Build a swept B-rep Body representing a straight road corridor.

```json
{
  "alignment_length_m": 300,
  "interval_m": 20,
  "lane_width_m": 3.65,
  "shoulder_width_m": 2.4,
  "lanes_each_side": 1,
  "crown_slope_pct": 2.0,
  "grade_pct": 0.0,
  "datum_elev_m": 10.0
}
```

Returns `face_count` and `shell_count`.

---

## Tool: `civil_corridor_volume`

Estimate pavement volume (m³) using prismatoid integration.

Assumes 0.5 m combined pavement + base course depth.

```json
{
  "alignment_length_m": 300,
  "lane_width_m": 3.65,
  "shoulder_width_m": 2.4
}
```

Returns `volume_m3`.

---

## Tool: `civil_corridor_ifc_alignment`

Return an `IfcAlignmentProduct` dict for IFC export.

```json
{
  "alignment_length_m": 300,
  "lane_width_m": 3.65,
  "shoulder_width_m": 2.4,
  "lanes_each_side": 1
}
```

Returns:

```json
{
  "ok": true,
  "ifc_dict": {
    "type": "IfcAlignmentProduct",
    "total_length_m": 300.0,
    "lane_width_m": 3.65,
    "shoulder_width_m": 2.4,
    "lanes_each_side": 1,
    "cut_slope_h_v": 2.0,
    "fill_slope_h_v": 2.0,
    "crown_slope_pct": 2.0
  }
}
```

Reference: ISO 16739-1:2018 — IfcAlignmentProduct; AASHTO Green Book.
