# Injection-Mold Tooling (`kerf-mold`)

## Overview

`kerf-mold` provides a seed implementation for injection-mold tooling design. It covers the core design rule checks an LLM agent needs to validate and generate an injection mold from a part description.

## Data Model

| Class | Description |
|---|---|
| `Face` | A planar or curved mold face: `vertices` (list of `[x,y,z]`), `normal` (unit outward normal), optional `face_id` label. |
| `EjectorPin` | Cylindrical ejector pin: `position`, `diameter_mm`, `length_mm`. |
| `GateLocation` | Gate entry: `point` `[x,y,z]`, `gate_type` (`edge` / `pin` / `submarine` / `direct` / `hot_tip`). |
| `PartingLine` | Closed loop of 3-D points bounding the parting surface (>= 3 points). |
| `MoldDesign` | Top-level assembly: `core_faces`, `cavity_faces`, `parting_line`, `pull_direction`, `ejector_pins`, `gate`, `wall_thicknesses_mm`. |

`pull_direction` is always normalised to unit length on construction.

## Design Functions

### `generate_parting_surface(parting_line, style, pull_dir, extrusion_depth_mm)`

Extends a closed parting-line loop into a surface patch.

- **`flat`** (default): projects all points onto the best-fit plane (Newell's method) and fan-triangulates from the centroid. Sets `is_flat=True` when all points lie within 1 µm of the plane.
- **`ruled`**: extrudes each parting-line edge along `pull_dir` by `extrusion_depth_mm` (default 50 mm), producing a ruled strip band.

Returns: `{ok, style, vertices, faces, area_mm2, is_flat, centroid, warnings}`.

### `check_moldability(mold_design, min_draft_deg, max_wall_ratio)`

Validates three moldability criteria:

1. **Draft angle** — every face must have `draft_deg >= min_draft_deg` (default 1°). Computed as `degrees(asin(n · pull_hat))`. Negative = undercut.
2. **Wall uniformity** — if `wall_thicknesses_mm` is provided, `max/min <= max_wall_ratio` (default 3.0). High ratios risk sink marks.
3. **Parting continuity** — best-fit plane normal of the parting line must be within 5° of the pull direction.

Returns: `{ok, all_checks_pass, checks, failing_faces, warnings}`.

### `draft_angle_per_face(faces, pull_dir)`

Computes `draft_deg = degrees(asin(n · pull_hat))` per face. Returns a list of `{face_id, draft_deg, is_undercut, normal}`.

## LLM Tools

| Tool name | Description |
|---|---|
| `mold_check_moldability` | Full moldability check (draft + wall + parting). |
| `mold_generate_parting_surface` | Generate flat or ruled parting surface from a parting-line loop. |
| `mold_draft_angle_per_face` | Draft angle for each face vs pull direction. |

## Typical Workflow

1. Define `core_faces` and `cavity_faces` with normals pointing outward from each half.
2. Define the `parting_line` as the boundary loop where core and cavity meet.
3. Set `pull_direction` to the mold-opening axis (e.g., `[0, 0, 1]` for Z-up opening).
4. Call `mold_check_moldability` to validate draft, wall, and parting.
5. Call `mold_generate_parting_surface` to produce the parting surface geometry.

## Design Rules

| Rule | Typical value | Source |
|---|---|---|
| Minimum draft angle | 1° – 3° (textured: 3° – 5°) | Menges et al. §6 |
| Wall thickness ratio | ≤ 3:1 | Rosato §5 |
| Parting plane deviation | ≤ 5° from pull axis | Menges et al. §4 |
| Ejector pin diameter | ≥ 2 mm | Menges et al. §7 |

## References

- Menges G., Michaeli W., Mohren P. *How to Make Injection Molds*, 3rd ed., Hanser 2001.
- Rosato D.V., Rosato M.G. *Injection Molding Handbook*, 3rd ed., Kluwer Academic 2000.
