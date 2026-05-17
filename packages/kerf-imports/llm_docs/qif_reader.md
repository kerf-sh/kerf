# QIF Reader — `qif_reader.py`

ISO 23952 / QIF 3.0 XML reader for Quality Information Framework inspection files. Extracts measured characteristics, feature geometry, datums, and pass/fail status. Pure Python — stdlib `xml.etree` only, no third-party dependencies.

---

## Standard

QIF (Quality Information Framework) 3.0, ISO 23952:2020. A schema-driven XML format for CMM measurement data, GD&T tolerances, and quality inspection plans used by PC-DMIS, Calypso, Metrolog X4, and compatible inspection software.

---

## Public entrypoint

### `parse_qif(data: str | bytes) → dict`

Parse a QIF XML document (string or bytes). Returns a plain dict — never raises.

**Supported QIF sections:**
- `QIFDocument/Product/PartSet` → part name
- `MeasuredCharacteristics` (from MeasurementResources) → characteristics with nominal, tolerances
- `Features` → point, line, plane, circle, cylinder, sphere features
- `DatumDefinitions` → datum labels
- `MeasurementResults/MeasuredCharacteristics` → actual values, deviations, pass/fail status

Unsupported elements are silently skipped; a `warnings` list notes any schema anomalies.

**Return schema (success):**
```json
{
  "ok": true,
  "part_name": "MyPart",
  "characteristics": [
    {
      "id": "char-001",
      "name": "Diameter_A",
      "type": "dimension",
      "nominal": 25.0,
      "upper_tol": 0.05,
      "lower_tol": -0.05,
      "actual": 25.02,
      "deviation": 0.02,
      "status": "PASS"
    }
  ],
  "features": [
    {
      "id": "feat-001",
      "name": "CylinderA",
      "type": "CylinderFeature",
      "nominal": {"center": [0,0,0], "axis": [0,0,1], "diameter": 25.0, "length": 50.0},
      "actual": {"center": [0.01, 0.0, 0.0], "axis": [0,0,1], "diameter": 25.02, "length": 50.1}
    }
  ],
  "datums": [
    {"id": "datum-A", "label": "A", "feature_id": "feat-001"}
  ],
  "summary": {
    "total": 5,
    "passed": 4,
    "failed": 1
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
from kerf_imports.qif_reader import parse_qif

# From file
with open("inspection_report.qif") as f:
    data = f.read()

doc = parse_qif(data)
if not doc["ok"]:
    print("Parse error:", doc["reason"])
else:
    print(doc["part_name"])
    print(f"{doc['summary']['failed']} failed characteristics")
    for char in doc["characteristics"]:
        if char["status"] == "FAIL":
            print(char["name"], char["deviation"])
```

```python
# Check features
for feat in doc["features"]:
    print(feat["type"], feat["name"])

# Check datums
for datum in doc["datums"]:
    print(datum["label"], "→", datum["feature_id"])
```

---

## LLM tool

**`import_qif`** — registered via `@register`; gated on `"imports.qif"` capability.

Accepts `file_id` pointing to a QIF file already uploaded to the project. Returns the same dict schema as `parse_qif` (large `features` lists may be truncated in the LLM payload).

---

## Notes

- Read-only: no write support.
- QIF 3.0 (ISO 23952:2020) is fully supported. QIF 2.1 and 1.0 may parse partially — characteristics and features will be extracted if the XML element names match the QIF 3.0 schema.
- Namespace handling: the parser strips all namespace URIs and matches on local element names, so both namespace-prefixed (`qif:QIFDocument`) and bare (`QIFDocument`) forms are accepted.
- Large QIF files (> 50 MB) are read with `xml.etree.ElementTree` parse (not iterparse); for very large files consider splitting the input.
- Coordinate system transforms referenced by features are resolved if the referenced CS element is present in the same document; unresolved references are stored as the raw ID string.

---

## Standard citation

ISO 23952:2020 — Quality Information Framework (QIF) — An Integrated Model for Manufacturing Quality Information, 3rd ed.
