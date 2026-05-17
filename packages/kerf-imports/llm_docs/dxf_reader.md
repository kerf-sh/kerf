# kerf-imports · dxf/reader.py

DXF R12 and R2000+ ASCII parser with multi-encoding fallback.

## Entrypoints

### `read_dxf(text: str) -> DxfDocument`

Parse a DXF file from a string.

```python
from kerf_imports.dxf.reader import read_dxf

doc = read_dxf(dxf_text)
# doc.entities: list of entity dicts
# doc.blocks:   dict {block_name: list[entity]}
# doc.layers:   list of layer names
# doc.warnings: list of strings
```

### `read_dxf_bytes(data: bytes) -> DxfDocument`

Parse from raw bytes with encoding waterfall:

1. UTF-8-BOM (`utf-8-sig`)
2. UTF-8
3. Latin-1 (`latin-1`)
4. Windows CP1252 (`cp1252`)

The first encoding that does not raise a `UnicodeDecodeError` is used.

```python
from kerf_imports.dxf.reader import read_dxf_bytes

with open("drawing.dxf", "rb") as f:
    doc = read_dxf_bytes(f.read())
```

## Supported entities

`LINE`, `LWPOLYLINE`, `POLYLINE` (with vertices), `CIRCLE`, `ARC`,
`TEXT`, `MTEXT`, `INSERT` (block reference), `BLOCK` / `ENDBLK`

## DXF tokenization

The reader tokenizes the file into group-code/value pairs:

```
  0       <- group code
SECTION   <- value
  2
ENTITIES
...
```

Group codes are integers; values are strings. The parser converts
well-known numeric codes (10, 20, 30, etc.) to floats automatically.

## `DxfDocument`

| Attribute | Type | Description |
|---|---|---|
| `entities` | list[dict] | Flat list of all model-space entities |
| `blocks` | dict[str, list] | Block definitions |
| `layers` | list[str] | All referenced layer names |
| `header` | dict | `$VARIABLE` values from the HEADER section |
| `warnings` | list[str] | Non-fatal parse issues |

## LLM tool: `import_dxf`

See `tools/import_dxf.py`. The tool calls `read_dxf_bytes` and routes
geometry to a `.sketch` file, annotations to a `.drawing` file.

## Standards reference

- AutoCAD DXF Reference (R12 / R2000+) — Autodesk Developer Network
