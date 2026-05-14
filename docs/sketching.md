# Sketching

Create 2D profiles with geometric and dimensional constraints, then extrude or revolve them into 3D solid bodies.

## The .sketch JSON format

A `.sketch` file is a self-contained JSON document that describes all geometry, constraints, and solver metadata:

```json
{
  "schema": "kerf.sketch.v1",
  "coordinateSystem": { "origin": [0, 0, 0], "axis": "Z" },
  "geometry": [
    { "id": "L1", "type": "line", "points": [["P0", "P1"]] },
    { "id": "C1", "type": "circle", "center": "P2", "radius": 10 }
  ],
  "points": [
    { "id": "P0", "x": 0, "y": 0 },
    { "id": "P1", "x": 50, "y": 0 },
    { "id": "P2", "x": 25, "y": 30 }
  ],
  "constraints": [
    { "type": "distance", "entityA": "L1", "value": 50 },
    { "type": "coincident", "entityA": "P0", "entityB": "P2" }
  ],
  "solver": { "engine": "planegcs", "status": "under-constrained" }
}
```

## Coordinate system

Sketches live on a work plane. By default the XY plane is used (`axis: "Z"`), meaning the sketch normal points in +Z. The `origin` field sets the sketch's base point in model space. When a sketch is placed on a face (3D backdrop), the coordinate system aligns to that face's plane.

Units are millimeters. All geometry exists in model space, not normalized coordinates.

## Primitives

### Point

```json
{ "id": "P0", "x": 0, "y": 0 }
```

Standalone reference points used as construction geometry or constraint anchors.

### Line

```json
{ "id": "L1", "type": "line", "points": [["P0", "P1"]] }
```

Two-point segments. Chain lines by sharing an endpoint point. The solver treats each segment independently; use `coincident` constraints to connect them.

### Arc

```json
{ "id": "A1", "type": "arc", "start": "P0", "end": "P1", "center": "PC", "radius": 15 }
```

Three-point arc or center-plus-endpoints. The `start` and `end` fields reference point IDs. The arc direction (CW/CCW) is inferred from constraint context.

### Circle

```json
{ "id": "C1", "type": "circle", "center": "P0", "radius": 10 }
```

Center point + radius. Dimensional constraints (`radius`, `diameter`) can be applied.

### Ellipse

```json
{ "id": "E1", "type": "ellipse", "center": "P0", "radiusX": 20, "radiusY": 10 }
```

Full ellipse defined by center point and semi-axes.

### B-spline

```json
{ "id": "B1", "type": "bspline", "controlPoints": ["P0", "P1", "P2", "P3"], "degree": 3 }
```

Non-uniform rational B-spline (NURBS). Control points are point IDs. The `degree` defaults to 3 (cubic). B-splines can represent complex curves that are difficult to construct from primitive arcs.

### Polyline

```json
{ "id": "PL1", "type": "polyline", "points": ["P0", "P1", "P2", "P3"] }
```

A run of connected line segments sharing endpoints. Equivalent to chained lines but stored as a single entity.

## Constraints

Constraints are classified as **geometric** (quality) or **dimensional** (size). The `planegcs` solver (a FreeCAD PlaneGCS port) finds point coordinate assignments that satisfy all constraints simultaneously.

### Geometric constraints

| Constraint    | Selection                          | Meaning                                  |
|---------------|------------------------------------|------------------------------------------|
| coincident    | point + point, or point + curve     | Snap one point onto another point or curve |
| parallel      | line + line                        | Lines share the same direction           |
| perpendicular | line + line                        | 90° angle between lines                  |
| tangent       | line + circle/arc, or circle + circle | External tangency at point of contact  |
| equal length  | line + line, or arc + arc          | Identical size                           |
| equal radius  | circle + circle, or arc + arc      | Identical radius                         |
| symmetric     | point + point, line + line          | Mirror symmetry about a centerline       |
| fix           | any entity                         | Lock entity at its current position      |
| horizontal    | line                               | Force line to be horizontal              |
| vertical      | line                               | Force line to be vertical                |

```json
{ "type": "parallel", "entityA": "L1", "entityB": "L2" }
```

### Dimensional constraints

| Constraint | Selection                      | Parameter         |
|------------|--------------------------------|-------------------|
| distance   | point + point, or line + line  | Length in mm      |
| angle      | line + line                    | Angle in degrees  |
| radius     | circle, arc                    | Radius in mm      |
| diameter   | circle                         | Diameter in mm    |

```json
{ "type": "distance", "entityA": "L1", "value": 25.5 }
```

## Pattern operations

### Mirror

Mirror geometry about a centerline (axis entity):

```json
{ "type": "mirror", "entities": ["L1", "C1"], "axis": "L_mirror" }
```

### Linear pattern

Duplicate entities along a direction vector:

```json
{ "type": "pattern_linear", "entities": ["L1"], "direction": [1, 0, 0], "count": 5, "spacing": 10 }
```

### Polar pattern

Duplicate entities around a center point:

```json
{ "type": "pattern_polar", "entities": ["L1"], "center": "PC", "count": 6, "angle": 360 }
```

## Trim, extend, offset

These operations modify existing curves in-place:

- **trim** — Cut a curve at its intersection with another curve
- **extend** — Lengthen a line or arc to meet another curve or a distance
- **offset** — Create a curve parallel to the source at a given distance

```json
{ "type": "trim", "target": "L1", "tool": "A1" }
```

```json
{ "type": "extend", "entity": "L1", "length": 20 }
```

```json
{ "type": "offset", "source": "C1", "distance": 5, "side": "outside" }
```

## External geometry projection

Reference edges from 3D geometry into the sketch. Projected entities are treated as construction geometry (not solvable):

```json
{
  "type": "external_projection",
  "source": { "type": "edge_ref", "file_id": "part-uuid", "object_id": "body-uuid", "edge_index": 0 },
  "projected": { "type": "line", "points": [["P_proj_start", "P_proj_end"]] }
}
```

When the source 3D geometry changes, the projection updates automatically.

## Multi-loop holes

A single sketch profile can contain multiple closed loops. The outer loop defines the solid boundary; inner loops become holes:

```json
{
  "geometry": [
    { "id": "outer", "type": "polyline", "points": ["P0", "P1", "P2", "P3"], "closed": true },
    { "id": "hole1", "type": "circle", "center": "PH1", "radius": 5 },
    { "id": "hole2", "type": "circle", "center": "PH2", "radius": 3 }
  ]
}
```

On extrusion, the solver treats counter-clockwise loops as holes and clockwise loops as solid boundaries.

## Solver behavior

The `planegcs` solver reports one of three states:

| Status             | DOF count | Meaning                                   |
|--------------------|-----------|-------------------------------------------|
| `fully-constrained` | 0         | All degrees of freedom resolved           |
| `under-constrained`| > 0       | Geometry can still move; add constraints  |
| `over-constrained` | n/a       | Conflicting constraints; solver ignores one |

Entity colors in the viewport reflect solver state:
- **Black** — fully constrained, will not drag
- **Blue** — under-constrained, free to drag
- **Red** — over-constrained or contradictory

Drag a blue point to explore the design space interactively; the solver finds the nearest valid configuration each frame.

## LLM tools

Chat can create and modify sketches using these tools:

| Tool               | Purpose                                        |
|--------------------|------------------------------------------------|
| `create_sketch`    | Seed a new empty sketch file                   |
| `sketch_add_point` | Add a point entity                             |
| `sketch_add_line`  | Add a line between two point IDs               |
| `sketch_add_arc`   | Add an arc (start/end/center or 3-point)       |
| `sketch_add_circle`| Add a circle with center and radius            |
| `sketch_add_constraint` | Apply a geometric or dimensional constraint |
| `sketch_trim`      | Trim a curve at an intersection                |
| `sketch_extend`    | Extend a curve to meet another or a distance   |
| `sketch_offset`    | Offset a curve by a distance                   |
| `sketch_mirror`    | Mirror entities about an axis                  |
| `sketch_pattern_linear` | Create a linear pattern                   |
| `sketch_pattern_polar`  | Create a polar pattern                    |
| `sketch_add_bsp line`   | Add a B-spline                          |
| `sketch_add_ellipse`    | Add an ellipse                        |

## Exporting to JSCAD

Import a compiled sketch into a `.jscad` file:

```js
import profile from '/sketches/flange.sketch'
import { extrusions } from '@jscad/modeling'

export default function () {
  const flange = extrusions.extrudeLinear({ height: 10 }, profile())
  return [{ id: 'flange', geom: flange }]
}
```

The imported function returns a fresh Geom2 each call, compatible with `extrudeLinear`, `extrudeRotate`, sweep, and boolean operations.

## Related

- [Assemblies](./assemblies.md) — placing extruded sketches in 3D scenes
- [Parts & Objects](./concepts.md) — the JSCAD file model
- [Drawings](./drawings.md) — 2D drawing output from 3D models