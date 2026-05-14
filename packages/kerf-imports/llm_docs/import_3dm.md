# Rhino .3dm Import / Export

Kerf reads and writes Rhino `.3dm` files via the `rhino3dm` library (McNeel,
BSD/MIT). This lets every existing Rhino user drop their `.3dm` library directly
into Kerf without any format conversion step.

## Supported Rhino object types

| Rhino type | Kerf kind | Notes |
|---|---|---|
| `Brep`, `Extrusion`, `SubD` | `.feature` | v1 stores the serialised rhino3dm BRep JSON; OCCT conversion is deferred. Always carries `source: "rhino3dm"`. |
| `NurbsCurve`, `LineCurve`, `ArcCurve`, `PolylineCurve`, `PolyCurve` | `.sketch` | Planar curves and 3-D wire curves. |
| `NurbsSurface`, `RevSurface`, `PlaneSurface` | `.surf` | Standalone surfaces (not trimmed into a BRep). |
| `Mesh` | `.mesh` | Polygon mesh, same shape as Kerf's native mesh format. |
| `Point`, `PointCloud` | `.point` | 3-D point or cloud; stored as `{x, y, z}`. |
| `InstanceReference` | metadata only | Block instances are captured as `{source, kind: "instance", instance_definition_index}`. Full block expansion is v2 scope. |

Objects whose type is not in the table above are silently skipped; they do not
generate an error.

## LLM tools

### `import_3dm`

Imports a `.3dm` binary that has already been uploaded to blob storage.

**Arguments**

```json
{
  "project_id": "<uuid>",
  "file_blob_id_or_storage_key": "uploads/abc123/model.3dm",
  "import_folder": "/rhino_import"
}
```

`import_folder` defaults to `/rhino_import` if omitted.

**Returns**

```json
{
  "created_files": [
    { "file_id": "<uuid>", "name": "wall0.feature", "kind": "feature", "rhino_kind": "feature" },
    { "file_id": "<uuid>", "name": "profile0.sketch", "kind": "sketch", "rhino_kind": "sketch" }
  ],
  "stats": { "count_by_kind": { "feature": 4, "sketch": 2, "mesh": 1 } },
  "import_folder": "/rhino_import",
  "layers": [{ "id": "...", "name": "Walls", "full_path": "Walls" }]
}
```

### `export_3dm`

Exports a selection of Kerf files back to a `.3dm` binary.

**Arguments**

```json
{
  "project_id": "<uuid>",
  "file_ids": ["<uuid1>", "<uuid2>"],
  "output_filename": "my_model.3dm"
}
```

**Returns**

```json
{
  "storage_key": "exports/<project_id>/<run_uuid>/my_model.3dm",
  "download_url": "https://cdn.example.com/...",
  "filename": "my_model.3dm",
  "size_bytes": 204800
}
```

## Example transcript

**User:** import library.3dm

**Assistant:**
1. Calls `import_3dm` with the blob key from the upload step.
2. Tool returns 12 features, 4 sketches, 3 meshes across layers "Walls", "Roof", "Structural".
3. Files are created under `/rhino_import/`.

```
✓ Imported 19 objects from library.3dm

  /rhino_import/wall0.feature    (feature, layer: Walls)
  /rhino_import/wall1.feature    (feature, layer: Walls)
  ...
  /rhino_import/profile0.sketch  (sketch, layer: Structural)
  /rhino_import/hull.mesh        (mesh, layer: Roof)

Stats: feature×12, sketch×4, mesh×3
```

**User:** export the structural sketches as a Rhino file

**Assistant:**
1. Lists the `.sketch` files under the Structural layer.
2. Calls `export_3dm` with their `file_id`s and `output_filename: "structural_sketches.3dm"`.
3. Returns a download URL valid for 1 hour.

## Data pipeline

```
Upload → blob storage (storage_key)
         ↓
         import_3dm  → POST pyworker /import-3dm
                        ↓
                        rhino3dm.File3dm.Read()
                        Walk model.Objects → classify → serialize
                        ↓
                     JSON response
                        ↓
                     DB INSERT per object → file tree
```

## Caveats (v1)

- BRep geometry is stored as the raw rhino3dm JSON encoding.
  Parametric feature operations (fillet, chamfer, boolean) are not available
  on imported BReps until OCCT conversion is implemented (deferred to v2).
- Block / InstanceReference expansion is metadata-only; the block geometry
  is not duplicated into Kerf files.
- Very large files (> 500 MB) may time out in pyworker (120 s limit).
- `rhino3dm` must be installed in the pyworker environment (`pip install rhino3dm`).
  If it is absent, the import endpoint returns an error payload instead of raising.
