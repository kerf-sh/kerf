# DFM — Design for Manufacture Checks

Pure-Python geometric DFM audit for CNC milling, injection moulding, die casting, and
3-D printing.  No OCC dependency.  Never raises.  Uses NumPy for mesh analysis.

---

## When to use

Keywords: DFM, design for manufacture, manufacturability, thin wall, wall thickness,
draft angle, undraft, undercut, die cast, injection moulding, injection molding, mold
draft, sharp corner, machinability, machinability score, DFM audit, pocket depth.

---

## Entrypoints

### `dfm_audit(part, process, pull_direction) -> dict`

Full DFM check suite.  Runs all checks appropriate for the chosen process.

**Parameters:**
- `part` — dict with optional keys:
  - `mesh` — `{"vertices": [[x,y,z],...], "triangles": [[i,j,k],...]}` (required for thin-wall check)
  - `edges` — `[{"a": [x,y,z], "b": [x,y,z], "angle_deg": float}, ...]` (interior angle at each edge)
  - `faces` — `[{"normal": [nx,ny,nz], "centroid": [cx,cy,cz], "area": float}, ...]`
  - `bounding_box` — `{"min": [x,y,z], "max": [x,y,z]}`
  - `deep_pockets` — `[{"depth": float, "width": float}, ...]`
  - `thin_wall_count` — `int`
- `process` — `"cnc_milling"` (default) | `"injection_moulding"` | `"die_casting"` | `"3d_printing"`
- `pull_direction` — `[dx, dy, dz]` demould axis (required for moulding/casting; defaults to `[0,0,1]`)

**Returns:**
```json
{
  "ok": true,
  "process": "cnc_milling",
  "score": 0.85,
  "issues": [
    {
      "kind": "thin_wall",
      "position": [x, y, z],
      "severity": "error|warning|info",
      "value": 0.3,
      "suggestion": "..."
    }
  ],
  "summary": "cnc_milling: 0 error(s), 2 warning(s). Machinability score: 0.85/1.0."
}
```

Issues sorted: errors first, then warnings, then info.  `ok=true` only when zero errors.

---

### `wall_thickness_min(mesh_or_solid, threshold_mm) -> list[dict]`

Detect thin-wall regions via ray casting (inward-normal rays between opposing faces).

- `mesh_or_solid` — `{"vertices": [...], "triangles": [...]}`
- `threshold_mm` — minimum acceptable thickness (default `1.0` mm)
- Returns list of `kind="thin_wall"` issue dicts; `severity="error"` when `< 0.5 × threshold`.

---

### `sharp_internal_corners(edges, threshold_deg) -> list[dict]`

Flag concave (interior) edges whose angle is below `threshold_deg`.

- `edges` — `[{"a": [x,y,z], "b": [x,y,z], "angle_deg": float}, ...]`
  - `angle_deg` is the **interior** angle (convex exterior > 180°; concave interior < 180°)
- `threshold_deg` — default `30.0°`
- Returns list of `kind="sharp_corner"` issue dicts.

---

### `no_draft_faces(faces, pull_direction, required_draft_deg) -> list[dict]`

Flag faces with insufficient draft (injection moulding / die casting only).

- `faces` — list of `{normal, centroid, area}` dicts
- `pull_direction` — demould axis
- `required_draft_deg` — default `0.5°`

---

### `undercut_regions(faces, pull_direction) -> list[dict]`

Flag faces with negative draft (undercuts that require side-action cores).

---

### `machinability_score(part) -> float`

Returns a score in `[0.0, 1.0]` (higher = easier to machine) based on face count,
bounding-box aspect ratio, deep-pocket depth/width ratio, and thin-wall count.

---

## Process defaults

| Process | Min wall (mm) | Draft (°) | Sharp corner (°) |
|---|---|---|---|
| `cnc_milling` | 0.5 | 0 (N/A) | 30 |
| `injection_moulding` | 1.5 | 1.5 | 45 |
| `die_casting` | 1.0 | 1.0 | 30 |
| `3d_printing` | 0.8 | 0 (N/A) | 20 |

---

## LLM tool names

| Tool | Function |
|---|---|
| `dfm_audit` | Full audit for one process |
| `dfm_wall_thickness` | Thin-wall check only (accepts `mesh` + `threshold_mm`) |

---

## Usage snippets

```python
from kerf_cad_core.dfm.checks import dfm_audit

part = {
    "mesh": {"vertices": [...], "triangles": [...]},
    "bounding_box": {"min": [0,0,0], "max": [100,50,30]},
}
result = dfm_audit(part, process="cnc_milling")
# result["ok"], result["score"], result["issues"]
```

```python
# Injection moulding with demould axis
result = dfm_audit(
    part,
    process="injection_moulding",
    pull_direction=[0, 0, 1],
)
# Checks thin wall, sharp corners, draft, AND undercuts.
```

```python
from kerf_cad_core.dfm.checks import machinability_score
score = machinability_score({"deep_pockets": [{"depth": 40, "width": 8}]})
# → penalised for depth/width ratio of 5 → score ≤ 0.80
```

---

## References

Boothroyd, G., Dewhurst, P., Knight, W. *Product Design for Manufacture and Assembly*, 3rd ed.

Kalpakjian, S. & Schmid, S. R. *Manufacturing Engineering & Technology*, 7th ed.
