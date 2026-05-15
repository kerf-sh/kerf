# IFC Export — `export_ifc` tool

Exports a Kerf `.bim` building model to an IFC 2x3/IFC4 STEP-physical-file
(`.ifc`).  Pure-Python; no proprietary IFC SDK required.

## LLM tool

```
export_ifc(project_id, bim_file_id?, model?, schema?, output_path?)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `project_id` | string | required | UUID of the Kerf project |
| `bim_file_id` | string | — | File ID of an existing `.bim` file to export |
| `model` | object | — | Inline `.bim` model dict (alternative to `bim_file_id`) |
| `schema` | `"IFC2X3"` \| `"IFC4"` | `"IFC2X3"` | IFC schema version |
| `output_path` | string | — | Project-tree path for the `.ifc` output file |

One of `bim_file_id` or `model` is required.

When `output_path` is provided, the IFC file is written to the project tree
and the response includes `{ ifc_path, file_id, entity_count, schema, warnings }`.

When `output_path` is omitted, the IFC text is returned inline in
`{ ifc_text, entity_count, schema, warnings }`.

## Tier 1 coverage (shipped)

| .bim element | IFC entity |
|---|---|
| `levels[]` | `IfcBuildingStorey` (with `IfcLocalPlacement`, elevation) |
| `walls[]` | `IfcWallStandardCase` (IFC2X3) / `IfcWall` (IFC4) with rect-profile extrusion |
| `slabs[]` | `IfcSlab` with arbitrary-closed-profile extrusion |
| `openings[]` kind=`"door"` | `IfcDoor` with rect-profile extrusion |
| `openings[]` kind=`"window"` | `IfcWindow` with rect-profile extrusion |
| `columns[]` | `IfcColumn` with rect-profile extrusion |
| `beams[]` | `IfcBeam` with rect-profile extrusion along axis |
| spatial root | `IfcProject → IfcSite → IfcBuilding → IfcBuildingStorey` |

## IFC structure produced

```
IfcProject
  └── IfcSite          (IfcRelAggregates)
        └── IfcBuilding (IfcRelAggregates)
              └── IfcBuildingStorey (one per .bim level)
                    └── [elements] (IfcRelContainedInSpatialStructure)
```

Every element has:
- `IfcLocalPlacement` relative to its storey placement
- `IfcExtrudedAreaSolid` body representation
- `IfcOwnerHistory` reference

## Units

The `.bim` model stores all dimensions in **millimetres**.  The IFC file uses
**SI metres** (`IfcSIUnit(*,.LENGTHUNIT.,$,.METRE.)`).  All coordinates and
dimensions are divided by 1000 during export.

## Schema header

```
ISO-10303-21;
HEADER;
FILE_DESCRIPTION(('Kerf BIM IFC Export'),'IFC2X3');
FILE_NAME('My Project','2025-01-01T00:00:00',('Kerf'),('Kerf'),'Kerf BIM Exporter','Kerf BIM','');
FILE_SCHEMA(('IFC2X3'));
ENDSEC;
DATA;
...
ENDSEC;
END-ISO-10303-21;
```

## Round-trip compatibility

The export schema matches the import module's `.bim` model shape
(`kerf_bim.import_ifc`) so a round-trip is feasible:

```
import_ifc → IFCImportResult.bim_payload → export_ifc → .ifc file
```

Geometry fidelity is Tier 1: walls are rect-profile extrusions; slab
boundaries are preserved as arbitrary closed profiles.

## Validation

The exporter runs a lightweight in-process validation pass:
- File terminates with `ENDSEC; END-ISO-10303-21;`
- All `#N` references used in entity attributes are defined in the DATA section

Non-fatal validation issues are reported in `warnings`.
