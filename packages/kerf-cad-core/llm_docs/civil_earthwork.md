# Civil Earthwork & Site Grading

Tools for terrain modelling, design surface definition, and cut/fill volume
computation for civil/site work.

## Workflow

1. `civil_terrain` — load survey points → TIN stats
2. `civil_pad` — define proposed pad → design surface config
3. `civil_earthwork` — compute cut/fill volumes
4. `civil_grading_report` — format balance report

---

## Tools

### `civil_terrain`

Build a TIN from survey points and return surface statistics.

```json
{
  "points": [
    {"x": 0, "y": 0, "z": 100.0},
    {"x": 10, "y": 0, "z": 101.5},
    {"x": 10, "y": 10, "z": 102.0},
    {"x": 0, "y": 10, "z": 100.5}
  ]
}
```

Returns: `{ok, point_count, triangle_count, area_m2, min_elevation_m, max_elevation_m, elevation_range_m}`

Errors: `{ok: false, errors: [...]}` for < 3 points or collinear inputs.

---

### `civil_pad`

Define a flat or sloped design platform.

```json
{
  "polygon": [[0,0],[20,0],[20,15],[0,15]],
  "pad_elevation": 101.0,
  "side_slope_ratio": 2.0
}
```

`side_slope_ratio`: horizontal run per 1 m vertical (e.g. `2.0` = 1V:2H).
Set to `0` for vertical pad edges (no grading outside polygon).

For a tilted pad add `"sloped": true, "dz_dx": 0.01, "dz_dy": 0.005`.

Returns: `{ok, design_surface_json, ...}` — pass `design_surface_json` to
`civil_earthwork`.

---

### `civil_earthwork`

Compute cut/fill volumes between existing ground and proposed pad.

```json
{
  "tin_points": [...],
  "design_surface": <design_surface_json from civil_pad>,
  "grid_spacing_m": 1.0
}
```

Returns:
```json
{
  "ok": true,
  "cut_m3": 245.3,
  "fill_m3": 198.7,
  "net_m3": -46.6,
  "balance_ratio": 1.234,
  "sample_count": 320,
  "grid_spacing_m": 1.0,
  "note": "More cut than fill — surplus material to export."
}
```

`balance_ratio = cut / fill`. Ratio ≈ 1.0 means balanced earthwork.

---

### `civil_grading_report`

Format a human-readable grading report.

```json
{
  "earthwork": <civil_earthwork output>,
  "project_name": "Site A - Pad 3",
  "site_description": "Proposed warehouse pad, 20×15 m"
}
```

Returns `{ok, report_text, summary_lines}`.

---

## Notes

- All coordinates in **metres**; volumes in **m³**.
- TIN method: fan triangulation from lexicographic first point — deterministic.
- Volume method: grid sampling; default spacing 1.0 m; reduce to 0.5 m for
  higher accuracy on small sites.
- All tools return `{ok: false, errors: [...]}` on invalid input; never raise.
