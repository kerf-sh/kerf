# Site Geometry — LLM Reference

TIN terrain B-rep and earthwork cut/fill analysis.

## Tool: `bim_toposolid_to_brep`

Build a closed B-rep Body from a triangulated terrain (Toposolid).

```json
{
  "points": [
    [0, 0, 0], [10, 0, 0], [10, 10, 0],
    [0, 10, 0], [5, 5, 1]
  ],
  "material": "soil",
  "thickness": 1.0
}
```

The body consists of:
- TIN top faces (one per Delaunay simplex)
- Vertical side faces connecting boundary edges to the base plane
- Flat base faces at `min_z - thickness`

Returns `face_count`, `simplex_count`, `shell_closed`.

---

## Tool: `bim_cut_fill_volume`

Grid-difference earthwork volumes between existing and proposed grades.

```json
{
  "existing_points": [[0,0,1],[10,0,1],[10,10,1],[0,10,1],[5,5,1]],
  "proposed_points": [[0,0,0],[10,0,0],[10,10,0],[0,10,0],[5,5,0]],
  "grid_spacing": 1.0
}
```

Returns:

```json
{
  "ok": true,
  "cut": 100.0,
  "fill": 0.0,
  "net": -100.0
}
```

- `cut` — material removed (m³)
- `fill` — material added (m³)
- `net = fill - cut` (positive = net fill)

Reference: ASCE 32-01; Revit Architecture 2024 Toposolid.
