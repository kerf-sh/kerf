# kerf-imports · dxf_writer.py

DXF R12 / R2004 export from Kerf drawing documents.

## Entrypoints

### `dxf_export(doc, version="R2004") -> str`

Converts a Kerf drawing document to DXF text.

```python
from kerf_imports.dxf_writer import dxf_export

dxf_text = dxf_export(drawing_doc, version="R2004")
```

Supported versions:
- `"R12"` — DXF AC1009 (AutoCAD Release 12, widest compatibility)
- `"R2004"` — DXF AC1018 (AutoCAD 2004, default; supports LWPOLYLINE/MTEXT)

### `dxf_export_result(doc, version="R2004") -> dict`

Wrapped version for LLM tool use.

```python
result = dxf_export_result(drawing_doc)
# result: {ok, dxf, reason}
```

## Supported entities

| Entity | R12 | R2004 | Notes |
|---|---|---|---|
| LINE | yes | yes | |
| POLYLINE | yes | yes | 3D-compatible |
| LWPOLYLINE | no | yes | Lightweight polyline |
| CIRCLE | yes | yes | |
| ARC | yes | yes | |
| ELLIPSE | no | yes | |
| SPLINE | no | yes | Degree-3 B-spline |
| TEXT | yes | yes | Single-line |
| MTEXT | no | yes | Multi-line |
| DIMENSION | yes | yes | |
| HATCH | no | yes | |
| INSERT / BLOCK | yes | yes | Block references |
| LEADER | yes | yes | |

## LLM tool: `export_dxf`

```json
{"file_id": "uuid", "version": "R2004"}
```

Returns: `{ok, blob_id, byte_count, entity_count, version, warnings}`.

## Notes

- Layer names are preserved from the source drawing.
- Coordinate values are in millimetres; DXF unit header `INSUNITS=4` (mm)
  is written for R2004.
- For DXF import (round-trip), see `kerf_imports.dxf.reader`.

## Standards reference

- AutoCAD DXF Reference AC1009 (R12) — Autodesk
- AutoCAD DXF Reference AC1018 (2004) — Autodesk
