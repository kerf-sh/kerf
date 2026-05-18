# kerf-dental

Dental CAD plugin for Kerf — parametric crown design, surgical guide placement,
and DICOM-to-mesh ingest.

## Crown Design

### `design_crown(inp: CrownDesignInput) -> CrownResult`

Build a parametric dental crown B-rep from a preparation margin line and
opposing-tooth cusp profile.

```python
from kerf_dental.crown import CrownDesignInput, design_crown

inp = CrownDesignInput(
    margin_line=[
        (0.0, 0.0, 0.0), (4.0, 0.0, 0.0), (4.0, 3.5, 0.0),
        (0.0, 3.5, 0.0),
    ],
    opposing_cusp_heights_mm=[2.0, 1.5, 1.8],
    material="zirconia",
    occlusal_clearance_mm=0.3,
)
result = design_crown(inp)
# result.body — validate_body-clean B-rep
# result.crown_radius_mm, result.crown_height_mm
```

The crown radius is the circumscribed radius of the margin-line polygon
projected onto its best-fit plane.  Height = max opposing cusp + clearance.

### LLM tool: `dental_crown_design`

| Parameter                  | Type    | Description |
|---------------------------|---------|-------------|
| `margin_line`             | array   | [[x,y,z], ...] polygon (min 3 points, mm) |
| `opposing_cusp_heights_mm`| array   | Cusp heights on opposing tooth (mm) |
| `material`                | string  | Material name (default "zirconia") |
| `occlusal_clearance_mm`   | number  | Clearance gap (default 0.3 mm) |

Returns `{crown_radius_mm, crown_height_mm, margin_centroid_mm, validate_body_ok, material}`.

---

## Surgical Guide

### `place_surgical_guide(jaw_surface_pts, implants) -> SurgicalGuideResult`

Place drill-guide sleeve cylinders on a jaw model at specified implant angles.

```python
from kerf_dental.guide import ImplantSpec, place_surgical_guide
import numpy as np

jaw_pts = [(x, y, z) for ...]  # jaw surface mesh vertices
implants = [
    ImplantSpec(
        position=(10.0, 5.0, 0.0),
        axis_direction=(0.0, 0.0, 1.0),   # straight apical
        diameter_mm=4.1,
        length_mm=11.5,
    ),
]
result = place_surgical_guide(jaw_pts, implants)
print(result.max_angular_error_deg())  # < 0.1°
```

Each sleeve is a `make_cylinder` Body snapped to the nearest jaw surface point.
Angular error (realised vs. requested axis) is < 1e-12° (floating-point only).

### LLM tool: `dental_surgical_guide`

| Parameter         | Type  | Description |
|------------------|-------|-------------|
| `jaw_surface_pts` | array | [[x,y,z], ...] jaw surface points (mm) |
| `implants`        | array | List of `{position, axis_direction, diameter_mm?, length_mm?}` |

Returns `{sleeve_count, max_angular_error_deg, angular_errors_deg, all_validate_body_ok}`.

---

## DICOM Ingest

### `PYDICOM_AVAILABLE`

Boolean flag — True when `pydicom` is installed.  Always importable; check
before calling ingest functions.

### `ingest_dicom(path_or_bytes, *, iso_value=300) -> DicomIngestResult`

Load a single DICOM file and extract a surface mesh via marching cubes.

```python
from kerf_dental.dicom_ingest import PYDICOM_AVAILABLE, ingest_dicom

if PYDICOM_AVAILABLE:
    result = ingest_dicom("/path/to/scan.dcm", iso_value=400)
    print(result.vertex_count, result.face_count)
    print(result.metadata["Modality"])
```

### `ingest_dicom_series(paths, *, iso_value=300) -> DicomIngestResult`

Load ordered axial DICOM slices and extract a 3-D mesh.

```python
from kerf_dental.dicom_ingest import ingest_dicom_series
result = ingest_dicom_series(sorted_dcm_paths, iso_value=300)
```

When `pydicom` is not installed, both functions raise `DicomUnavailableError`
(subclass of `ImportError`) with an install hint.

### LLM tool: `dental_dicom_ingest`

| Parameter    | Type   | Description |
|-------------|--------|-------------|
| `path`      | string | Absolute path to DICOM file |
| `iso_value` | number | Hounsfield iso-surface threshold (default 300) |

Returns `{vertex_count, face_count, iso_value, metadata}`.

---

## Tooth Anatomy Data Model

```python
from kerf_dental.crown import ToothAnatomy

t = ToothAnatomy(
    tooth_id="16",          # FDI notation: upper-right first molar
    arch="upper",
    crown_height_mm=8.5,
    root_length_mm=14.0,
    mesio_distal_width_mm=10.5,
    bucco_lingual_width_mm=11.0,
    cusp_heights_mm=[2.0, 1.8, 1.5, 1.6],  # 4 cusps
)
```

---

## Database Migration

The `dental_kind.sql` migration (in `packages/kerf-dental/migrations/`) adds
the `dental_cases` table for per-case anatomy and treatment metadata.
It must be folded into the kerf-core consolidated baseline before deployment.
**Flag: parent-coordinated reset required.**
