# Authoring `.jscad` files

JSCAD Parts are the default Kerf modeling surface. A `.jscad` file
exports a function whose return is an array of Objects. Each Object
has an `id` (string) and a `geom` (a JSCAD geometry value).

This is the kind you edit MOST often — and you usually edit it via
`edit_file` with a tight unique substring, not via any dedicated tool.

## Canonical file shape

```js
const { primitives, booleans, transforms, extrusions, hulls } =
  require('@jscad/modeling')

const { cuboid, cylinder, sphere } = primitives.shapes ?? primitives
const { translate, rotateZ } = transforms
const { union, subtract, intersect } = booleans

module.exports = function () {
  const base = cuboid({ size: [40, 40, 10] })
  const peg  = translate([0, 0, 5],
    cylinder({ radius: 4, height: 20 }))

  return [
    { id: 'base', geom: base },
    { id: 'peg',  geom: peg },
  ]
}
```

The `[{id, geom}, ...]` return is canonical. Every entry is an
**Object**; `id` becomes its identity for assemblies and viewport
picking.

## Namespaced API

JSCAD's `@jscad/modeling` exposes a single root object. All operations
live under namespaces; importing them at the top is conventional.

| Namespace         | What it does                                              |
|-------------------|-----------------------------------------------------------|
| `primitives`      | `cuboid`, `cylinder`, `sphere`, `polyhedron`, `circle`, `rectangle`, `roundedCuboid`, `torus` |
| `transforms`      | `translate`, `rotate`, `rotateX/Y/Z`, `scale`, `mirror`   |
| `booleans`        | `union`, `subtract`, `intersect`                          |
| `extrusions`      | `extrudeLinear`, `extrudeRotate` (revolve), `project`     |
| `hulls`           | `hull`, `hullChain`                                       |
| `expansions`      | `offset`, `expand`                                        |
| `colors`          | `colorize`, `hsl2rgb`                                     |

Calls take an options object first, geometry last:

```js
extrusions.extrudeLinear({ height: 10 }, sketch2d)
booleans.subtract(base, peg)
transforms.translate([0, 0, 5], cylinder({ radius: 4, height: 20 }))
```

## Object identity

The `id` on each return entry is what assemblies reference and what
the Objects panel surfaces. Pick stable, descriptive ids (`base`,
`bracket-left`, `peg`). Don't use uuid-style randomness — assemblies
hard-link by id.

If you split a single Part into two, the user has to update any
assembly that referenced the old single Object — flag this in your
summary.

## Importing sketches

```js
const profile = require('/profile.sketch')

return [
  { id: 'wall', geom: extrusions.extrudeLinear({ height: 20 }, profile) },
]
```

Sketches resolve to a `Geom2`. `extrudeLinear` and `extrudeRotate`
both accept it.

## Importing other JSCAD files

```js
const parts = require('/parts.jscad')   // returns the array of Objects
const peg = parts.find(p => p.id === 'peg').geom
```

## Common edits

### Make a dimension parametric

Pull magic numbers into a top-of-file `params` block:

```js
const params = { width: 40, height: 10, peg_d: 8 }
const base = cuboid({ size: [params.width, params.width, params.height] })
```

Then a `set the width to 60` request becomes a one-line
`edit_file('"width": 40' → '"width": 60')`.

### Add a fillet (JSCAD path — no real B-rep round)

JSCAD doesn't expose a true fillet. Approximations:
- `roundedCuboid({ size, roundRadius })` — only useful for the whole
  outer shell.
- Boolean a quarter-cylinder along an edge to round it (visual fudge
  for renders, NOT for STEP export).

For a real fillet, use a `.feature` file (see `feature.md`).

### Add a new Object to an existing Part

`edit_file` to extend the return array:

```text
old:
  return [
    { id: 'base', geom: base },
  ]
new:
  return [
    { id: 'base', geom: base },
    { id: 'peg',  geom: translate([0,0,5], cylinder({ radius: 4, height: 20 })) },
  ]
```

Or use `duplicate_object` to clone a shape with a fresh id (the
duplicate_object tool understands the bracket-matched array literal
and writes a structurally-correct clone).

### Remove an Object from a Part

`delete_object` is the safe way (bracket-matched). `edit_file` works
too if the entry is a unique substring.

## Anti-patterns

- Don't return a single geometry instead of `[{id, geom}, ...]` — the
  rest of Kerf (assemblies, drawings, BOM) breaks.
- Don't `console.log` from JSCAD — the worker pipes errors to the
  problem panel; logs go nowhere useful.
- Don't use top-level `await` in a JSCAD module — the runner is
  synchronous.
- Don't reference Three.js directly. JSCAD's geometry is its own
  format; the renderer turns it into Three.js meshes.
