# QIF Reader — `qif_reader.py`

ISO 23952 / QIF 3.0 XML reader for Quality Information Framework files. Extracts measurement plans, feature definitions, tolerances, and measurement results.

---

## Standard

QIF (Quality Information Framework) 3.0, ISO 23952:2020. A schema-driven XML format for CMM measurement data, GD&T tolerances, and quality inspection plans used by DMIS, PC-DMIS, Calypso, and compatible inspection software.

---

## Public API

### `read_qif(path_or_fileobj) → QIFDocument`

Parse a `.qif` XML file or file-like object. Returns a `QIFDocument` dataclass.

`QIFDocument` fields:
```
version: str                      # "3.0"
measurement_plan: MeasurementPlan | None
features: list[QIFFeature]
tolerances: list[QIFTolerance]
measurement_results: list[MeasurementResult] | None
body_id: str | None               # UUID of the associated body/part
```

### `QIFFeature`

```python
@dataclass
class QIFFeature:
    id: str                  # UUID
    feature_type: str        # "Plane", "Cylinder", "Sphere", "Cone", "Line", "Circle", "Point"
    nominal: dict            # feature-type-specific nominal parameters
    coordinate_system: str   # reference CS id
```

### `QIFTolerance`

```python
@dataclass
class QIFTolerance:
    id: str
    tolerance_type: str      # "Flatness", "Cylindricity", "Position", "Angularity", etc.
    feature_ref: str         # references QIFFeature.id
    datum_refs: list[str]
    value_mm: float
    modifier: str | None     # "MMC", "LMC", "RFS", None
```

### `MeasurementResult`

```python
@dataclass
class MeasurementResult:
    feature_ref: str
    measured: dict           # actual measured parameters
    deviation_mm: float
    pass_: bool              # True = within tolerance
    status: str              # "PASS", "FAIL", "MARGINAL"
```

---

## Usage

```python
from kerf_imports.qif_reader import read_qif

doc = read_qif("inspection_report.qif")
print(doc.version)

for feat in doc.features:
    print(feat.feature_type, feat.nominal)

for tol in doc.tolerances:
    print(tol.tolerance_type, tol.value_mm)

if doc.measurement_results:
    fails = [r for r in doc.measurement_results if not r.pass_]
    print(f"{len(fails)} failures")
```

---

## Notes

- Read-only: no write support.
- Only QIF 3.0 schema is supported; earlier versions (2.1, 1.0) may parse partially.
- Large QIF files (>50 MB) are streamed with `xml.etree.ElementTree` iterparse to avoid memory issues.
- Coordinate system transforms are resolved if all referenced CS objects are present in the file; unresolved references are left as raw IDs.
