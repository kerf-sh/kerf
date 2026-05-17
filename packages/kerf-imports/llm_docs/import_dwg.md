# kerf-imports · tools/import_dwg.py

LLM tool: import a DWG file into a Kerf project via the libredwg bridge.

## LLM tool: `import_dwg`

```json
{
  "project_id": "uuid",
  "file_blob_id_or_storage_key": "blob_abc123",
  "import_folder": "/dwg_import",
  "expand_inserts": true
}
```

### Parameters

| Parameter | Required | Default | Description |
|---|---|---|---|
| `project_id` | yes | — | UUID of the target project |
| `file_blob_id_or_storage_key` | yes | — | Blob ID or storage key for the `.dwg` file |
| `import_folder` | no | `/dwg_import` | Folder path inside project tree |
| `expand_inserts` | no | `true` | Expand INSERT block references inline |

### Returns (success)

```json
{
  "created_files": [
    {"file_id": "uuid", "name": "import.sketch", "kind": "sketch"},
    {"file_id": "uuid", "name": "import.drawing", "kind": "drawing"}
  ],
  "stats": {"entities": 88, "annotations": 5, "blocks": 2, "warnings": 0, "loops": 7},
  "warnings": [],
  "import_folder": "/dwg_import",
  "bridge": {"available": true, "backend": "cli", "version": "0.12.5"}
}
```

## Conversion pipeline

```
.dwg bytes
  → libredwg bridge (Python binding or dwgread CLI)
  → DXF ASCII text
  → kerf_imports.dxf.reader.read_dxf()
  → kerf_imports.dxf.mapper.dxf_to_both()
  → Kerf .sketch / .drawing JSON payloads
```

The `bridge` key in the response reports which backend was used:
- `"python"` — libredwg Python binding (`import libredwg`)
- `"cli"` — `dwgread` command-line tool

## Bridge availability

Check: `get_bridge_info()` from `kerf_imports.dwg.bridge`.

If the bridge is unavailable, the tool returns:
```json
{
  "ok": false,
  "reason": "DWG bridge not available — install libredwg (pip install libredwg  OR  brew install libredwg)"
}
```

Supported DWG versions: R1.0 through AutoCAD 2018+ (all versions libredwg
can read).

## Error codes

| Code | Condition |
|---|---|
| `BAD_ARGS` | Missing required parameters |
| `DWG_BRIDGE_UNAVAILABLE` | libredwg not installed |
| `DWG_CONVERSION_ERROR` | libredwg conversion failed or produced empty output |
| `DXF_PARSE_ERROR` | DXF parse error after conversion |
| `DXF_MAPPING_ERROR` | Entity mapping error |
| `NOT_FOUND` | Blob not found in storage |
| `STORAGE_ERROR` | Storage backend error |
| `NO_STORAGE` | `ctx.storage` not configured |
