# kerf-imports · tools/import_dxf.py

LLM tool: import a DXF file (R12 or R2000+) into a Kerf project.

## LLM tool: `import_dxf`

```json
{
  "project_id": "uuid",
  "file_blob_id_or_storage_key": "blob_abc123",
  "import_folder": "/dxf_import",
  "expand_inserts": true
}
```

### Parameters

| Parameter | Required | Default | Description |
|---|---|---|---|
| `project_id` | yes | — | UUID of the target project |
| `file_blob_id_or_storage_key` | yes | — | Blob ID or storage key for the `.dxf` file |
| `import_folder` | no | `/dxf_import` | Folder path inside project tree |
| `expand_inserts` | no | `true` | Expand INSERT block references inline |

### Returns

```json
{
  "created_files": [
    {"file_id": "uuid", "name": "import.sketch", "kind": "sketch"},
    {"file_id": "uuid", "name": "import.drawing", "kind": "drawing"}
  ],
  "stats": {
    "entities": 142,
    "annotations": 8,
    "blocks": 3,
    "warnings": 0,
    "loops": 12
  },
  "warnings": [],
  "import_folder": "/dxf_import"
}
```

## Pipeline

1. Fetch blob bytes from `ctx.storage`.
2. POST to pyworker `/import-dxf` endpoint (60 s timeout).
3. pyworker parses entities → geometry payload (sketch) + annotation payload (drawing).
4. Create or resolve `import_folder` hierarchy in the project files tree.
5. Insert `.sketch` and/or `.drawing` rows into the `files` table.
6. Return created file IDs, stats, and any translation warnings.

## Entity mapping

| DXF entity | Output |
|---|---|
| LINE, LWPOLYLINE, POLYLINE | `.sketch` geometry |
| CIRCLE, ARC | `.sketch` geometry |
| TEXT, MTEXT | `.drawing` annotations |
| INSERT (with `expand_inserts=true`) | expanded geometry in `.sketch` |
| INSERT (with `expand_inserts=false`) | placeholder in `.sketch` |

If no geometry entities are present, the `.sketch` file is omitted.
If no annotation entities are present, the `.drawing` file is omitted.

## Error codes

| Code | Condition |
|---|---|
| `BAD_ARGS` | Missing required parameters |
| `NOT_FOUND` | Blob not found in storage |
| `STORAGE_ERROR` | Storage backend error |
| `DXF_FORMAT_ERROR` | pyworker returned HTTP 422 |
| `PYWORKER_ERROR` | pyworker returned other non-200 |
| `PYWORKER_UNREACHABLE` | Network/connection error to pyworker |
| `NO_STORAGE` | `ctx.storage` not configured |
