# 3DM Export (GK-P50)

Export a Kerf project or individual files as a Rhino `.3dm` binary.

Two routes are available:

1. **Project-level download** — `GET /api/projects/{pid}/export-3dm`
   Returns all feature/surf/sketch/mesh files as a single `.3dm` attachment.
   Mirrors the existing `/api/projects/{pid}/export` (ZIP) route.

2. **LLM tool** — `export_3dm` (in `kerf-imports`)
   Collects specified `file_ids`, posts to `/export-3dm`, stores the result in
   blob storage, and returns a `download_url`.

---

## When to use

- User asks to "download as Rhino", "save as 3DM", or "export to Rhino"
- Sending geometry to a Rhino/Grasshopper workflow
- Round-tripping NURBS surfaces with full control-point fidelity

---

## HTTP Route

`GET /api/projects/{pid}/export-3dm`

Returns a `model/vnd.3dm` binary attachment named `{project-slug}-{pid8}.3dm`.

Requires project read access. Uses the `rhino3dm` PyPI package when installed;
falls back to the minimal kerf fixture-format writer (understood by `read_3dm`).
Returns HTTP 503 when neither backend is available.

---

## LLM Tool

`export_3dm` (registered by `kerf-imports`):

**Required:** `project_id`, `file_ids` (non-empty list of file UUIDs)
**Optional:** `output_filename` (default "export.3dm")
**Returns:** `{storage_key, download_url, ...}`

---

## Notes

- The project-level route (`/export-3dm`) exports ALL feature/surf/sketch/mesh
  files; use the `export_3dm` LLM tool to export a specific subset.
- The `rhino3dm` PyPI package is an optional dependency. When absent, the
  minimal writer is used for round-trip with Kerf's own `read_3dm`.
- 3DM export does not include STL meshes (those are in the ZIP export); it
  exports NURBS geometry only.
