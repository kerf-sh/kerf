# Sketching

Author 2D profiles with geometric and dimensional constraints, then extrude
them into 3D from JSCAD.

## What a sketch is

A `.sketch` file is a JSON document describing:

- **Geometry** — points, lines, arcs, circles, polylines.
- **Constraints** — geometric (parallel, perpendicular, equal, tangent,
  coincident) and dimensional (distance, angle).
- A **solver** state — `planegcs` (a port of FreeCAD's PlaneGCS) finds an
  assignment of point coordinates that satisfies every constraint, and reports
  whether the system is fully constrained, under-constrained, or
  over-constrained.

The compiled output is a closed Geom2 region that `.jscad` files consume.

## Create a sketch

In the file tree, click **New file → Sketch**. The sketch editor opens with an
empty canvas, a toolbar of geometry tools, and a constraints palette.

<!-- screenshot: empty sketch canvas with toolbar -->

The chat side panel can call `create_sketch` to seed an empty sketch from
chat — but it cannot edit the sketch's geometry or constraints. That's a
human-driven loop on purpose: sketches are precise and visual; LLM-edited
sketches cause more pain than they save.

## Drawing tools

| Tool      | Use                                          |
|-----------|----------------------------------------------|
| Point     | Standalone reference points                  |
| Line      | Two-point segments (chain them by re-clicking the endpoint) |
| Arc       | Three-point or center+endpoints              |
| Circle    | Center + radius                              |
| Polyline  | A run of connected lines                     |
| Trim      | Cut a curve at intersections (planned)       |

Drawn geometry starts unconstrained — you can drag points around freely. As
you add constraints, the solver locks down the degrees of freedom.

## Constraints

Geometric and dimensional constraints, applied by selecting one or more
entities and clicking a constraint button.

### Geometric

| Constraint      | Selection                  | Meaning                                       |
|-----------------|----------------------------|-----------------------------------------------|
| Coincident      | 2 points                   | Snap one point onto the other                 |
| Horizontal      | 1 line                     | Force horizontal                              |
| Vertical        | 1 line                     | Force vertical                                |
| Parallel        | 2 lines                    | Same direction                                |
| Perpendicular   | 2 lines                    | 90° between them                              |
| Equal           | 2 segments / 2 circles     | Same length / same radius                     |
| Tangent         | line + circle, 2 circles   | Tangency at the point of contact              |

### Dimensional

| Constraint   | Selection             | Parameter            |
|--------------|-----------------------|----------------------|
| Distance     | 2 points or a segment | Length in model mm   |
| Angle        | 2 lines               | Angle in degrees     |
| Radius       | 1 circle / 1 arc      | Radius in model mm   |
| Diameter     | 1 circle              | Diameter in model mm |

## Examples

**Parallel + distance.** Two lines, parallel, 10 mm apart:

1. Draw the first line.
2. Draw the second roughly parallel.
3. Select both lines → click **Parallel**.
4. Select both lines → click **Distance**, type `10`.

**Perpendicular at a corner.** Two lines meeting at a point:

1. Draw both lines so they share an endpoint (snap to it).
2. Add a **Coincident** constraint on the shared endpoint.
3. Select both lines → click **Perpendicular**.

**Angled rib.** A line at 30° to a base line:

1. Draw the base line.
2. Draw the angled line.
3. Select both → click **Angle**, type `30`.

## Degree-of-freedom feedback

The sketch viewport colors entities by solver state:

- **Black** — fully constrained (zero DOF). Won't move on drag.
- **Blue** — under-constrained. Free to drag; missing constraints implied.
- **Red** — over-constrained or contradictory. The solver ignores conflicting
  constraints; fix or delete one.

The status bar shows the global DOF count and the last solver error, if any.

## Drag-to-solve

Grab a blue point and drag. The solver runs every frame, finding the nearest
configuration that still satisfies all the constraints. This is how you
explore design intent before locking it down.

## Exporting as a Geom2

A sketch always compiles to a Geom2 (closed loop). When you reference a
sketch from a JSCAD file:

```js
import profile from '/sketches/flange.sketch'
import { extrusions } from '@jscad/modeling'

export default function () {
  const flange = extrusions.extrudeLinear({ height: 10 }, profile())
  return [{ id: 'flange', geom: flange }]
}
```

The import returns a function that yields a fresh Geom2 each call, so you can
extrude, revolve, sweep, or boolean against it like any other 2D shape.

## Limits and roadmap

Today: planegcs solver, the constraints listed above, single closed loop per
sketch. Planned (see ROADMAP.md → "Sketcher v2"):

- Trim / extend / fillet (2D)
- Mirror, linear/polar pattern
- Ellipses and B-splines
- External geometry references
- 3D backdrop (sketch on a face of an existing body)
- Multi-loop holes inside an outer profile

Next: [assemblies.md](./assemblies.md)
