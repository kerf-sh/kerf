# Draft Workbench — .draft File Format

Orthogonal to the constraint-based Sketcher, the Draft workbench provides a
standalone 2D CAD format suitable for exploded views, site plans, schematic-style
diagrams, and general annotation.

## Schema

```json
{
  "version": 1,
  "name": "Floor Plan",
  "scale": 1.0,
  "entities": [ ... ]
}
```

`scale` is a multiplier applied to all coordinates (default `1.0`).

## Entity Reference

All entities carry an `id` (string). The `kind` field determines the remaining
fields.

### `line`
```json
{ "id": "l1", "kind": "line", "x1": 0, "y1": 0, "x2": 100, "y2": 0 }
```
Straight segment between `(x1,y1)` and `(x2,y2)`.

### `polyline`
```json
{ "id": "p1", "kind": "polyline", "points": [[0,0], [100,0], [100,50]], "closed": false }
```
Open or closed list of `[x, y]` vertex pairs. `closed: true` joins last→first.

### `arc`
```json
{ "id": "a1", "kind": "arc", "cx": 50, "cy": 50, "rx": 30, "ry": 30,
  "start_angle": 0, "end_angle": 90, "clockwise": false }
```
Elliptic arc on the principal axes. Angles in degrees.

### `circle`
```json
{ "id": "c1", "kind": "circle", "cx": 50, "cy": 50, "r": 20 }
```

### `spline`
```json
{ "id": "s1", "kind": "spline", "points": [[0,0], [50,100], [100,0]] }
```
Open B-spline through control points.

### `rect`
```json
{ "id": "r1", "kind": "rect", "x": 10, "y": 10, "w": 80, "h": 40, "rotation": 0 }
```
Axis-aligned rectangle with lower-left corner at `(x, y)`.

### `text`
```json
{ "id": "t1", "kind": "text", "x": 10, "y": 20, "value": "NOTE", "size": 12, "rotation": 0 }
```
Single-line annotation string.

### `dimension`
```json
{ "id": "d1", "kind": "dimension", "x1": 0, "y1": 0, "x2": 100, "y2": 0, "offset": 10, "label": "100" }
```
Linear dimension with leader offset and optional label override.

## Operations

| Function | Description |
|---|---|
| `defaultDraft(name)` | New empty document |
| `validateDraft(d)` | Returns `{ok, errors[]}` |
| `addEntity(d, entity)` | Appends entity; auto-assigns id |
| `removeEntity(d, id)` | Removes by id |
| `moveEntity(d, id, dx, dy)` | Translates entity |
| `offsetEntity(d, id, distance)` | Perpendicular offset — lines & polylines only; returns new entity or `null` |
| `trimEntity(d, id, boundary_id)` | Trims line at intersection with boundary line |
| `filletCorner(d, line1_id, line2_id, radius)` | Rounds corner with tangent arc; returns arc or `null` |
| `patternLinear(d, id, count, dx, dy)` | Array-copy; returns list of new entities |
| `patternPolar(d, id, count, center, total_angle_deg)` | Polar array around `[cx, cy]`; returns list of new entities |
| `exportDXF(d)` | R12 DXF text (HEADER / ENTITIES / EOF) |

## DXF Export Note

`exportDXF` emits **AutoCAD R12** (AC1009) with minimal entity support:
`LINE`, `CIRCLE`, `ARC`, `POLYLINE` (with `VERTEX`/`SEQEND`), and `TEXT`.
Other entity kinds are silently skipped.

---

## Examples

### 1 — Site Plan

```json
{
  "version": 1, "name": "Site Plan A", "scale": 1.0,
  "entities": [
    { "id": "boundary", "kind": "polyline", "points": [[0,0],[200,0],[200,150],[0,150]], "closed": true },
    { "id": "b1", "kind": "rect", "x": 20, "y": 20, "w": 60, "h": 40 },
    { "id": "b2", "kind": "rect", "x": 120, "y": 20, "w": 60, "h": 40 },
    { "id": "driveway", "kind": "polyline", "points": [[80,0],[120,0],[120,20],[80,20]], "closed": false },
    { "id": "label1", "kind": "text", "x": 50, "y": 35, "value": "Building A", "size": 14 }
  ]
}
```

### 2 — Exploded View

```json
{
  "version": 1, "name": "Motor Exploded", "scale": 1.0,
  "entities": [
    { "id": "housing", "kind": "circle", "cx": 0, "cy": 0, "r": 50 },
    { "id": "shaft", "kind": "line", "x1": 0, "y1": -80, "x2": 0, "y2": -150 },
    { "id": "key1", "kind": "rect", "x": -5, "y": -75, "w": 10, "h": 20 },
    { "id": "bolt1", "kind": "line", "x1": -40, "y1": -40, "x2": -55, "y2": -55 },
    { "id": "bolt2", "kind": "line", "x1": 40, "y1": -40, "x2": 55, "y2": -55 },
    { "id": "dim1", "kind": "dimension", "x1": -50, "y1": -50, "x2": 50, "y2": -50, "offset": 15, "label": "100" }
  ]
}
```

### 3 — Schematic-Style Diagram

```json
{
  "version": 1, "name": "Power Distribution", "scale": 1.0,
  "entities": [
    { "id": "bus", "kind": "line", "x1": 0, "y1": 50, "x2": 200, "y2": 50 },
    { "id": "r1", "kind": "rect", "x": 50, "y": 35, "w": 30, "h": 30 },
    { "id": "c1", "kind": "circle", "cx": 140, "cy": 50, "r": 15 },
    { "id": "gnd", "kind": "polyline", "points": [[80,65],[80,90],[70,90],[90,90]], "closed": false },
    { "id": "text_v", "kind": "text", "x": 5, "y": 45, "value": "+24V", "size": 12 },
    { "id": "arc1", "kind": "arc", "cx": 140, "cy": 50, "rx": 8, "ry": 8, "start_angle": 0, "end_angle": 180 }
  ]
}
```
