# Authoring `.equations` files

A `.equations` file holds a project-level table of named parameters
that get evaluated and injected into the JSCAD runner, the `.feature`
evaluator, and the `.sketch` solver. Use it whenever a model has a
shared dimension (wall thickness, hole spacing, screw pitch) that
multiple files need to agree on.

> **Tooling note:** Use `read_equations` to inspect the current set
> and `set_equation` to upsert a single param. For bulk edits / param
> deletion, edit the JSON file directly with `write_file` / `edit_file`
> after `read_file`-ing it.

## File shape

```json
{
  "version": 1,
  "params": [
    { "name": "wall_thickness", "expr": "2",                "unit": "mm", "comment": "Default wall" },
    { "name": "h",              "expr": "wall_thickness * 5", "unit": "mm" },
    { "name": "outer_radius",   "expr": "h / 2 + 3" }
  ]
}
```

Fields:

- `name` — JS-identifier-shaped (letters/digits/underscore, no leading
  digit). This is the binding the consuming files reference.
- `expr` — a [mathjs](https://mathjs.org/) expression. May reference
  earlier `params` by name. Most arithmetic, trig, and unit-free
  scalars work (`sin`, `cos`, `sqrt`, `pi`, `^`, `mod`).
- `unit` — display-only. Not used during evaluation. Suggest `"mm"`
  for lengths, `"deg"` for angles.
- `comment` — optional inline comment.

The frontend evaluator walks `params` in declaration order. If `expr`
references a name that hasn't been resolved yet, the row errors
(circular references show as `NaN` in the editor).

## Where the values flow

### JSCAD runner

The runner exposes the resolved values as `params` on the top-level
default-export argument:

```js
export default function ({ primitives, transforms, params }) {
  const { wall_thickness, h, outer_radius } = params || {}
  return [{ id: 'shell', geom: primitives.cylinder({ radius: outer_radius, height: h }) }]
}
```

### `.feature` files

Feature node fields can use `${name}` placeholders that are expanded
to the current evaluated number before the OCCT call:

```json
{
  "version": 1,
  "features": [
    { "id": "f1", "op": "pad", "sketch_path": "/profile.sketch", "height": "${h}", "direction": "up" }
  ]
}
```

The substitution is lexical — pass the placeholder as a string and the
runner replaces it with the numeric value at evaluate time. Mixing
literal arithmetic into the placeholder (`"${h * 2}"`) also works:
the bracketed substring is treated as a fresh mathjs expression
evaluated against the same scope.

### `.sketch` files

Dimensional constraint values (`distance`, `distance_x`, `distance_y`,
`angle`, `radius`, `diameter`) accept `${name}` strings the same way:

```json
{ "id": "c1", "type": "distance", "a": "p1", "b": "p2", "value": "${wall_thickness}" }
```

The sketcher UI shows the resolved number at the dimension label and
re-solves whenever the equations file changes.

## Multiple `.equations` files

Most projects use a single `params.equations` at the root. If a
project has more than one `.equations` file, they are all loaded and
merged into a single scope; **last loaded wins** per duplicate name
(file order is alphabetical by full path). The editor surfaces a
warning when a duplicate name is detected.

## Gotchas

- Units are display-only — the evaluator works in dimensionless
  numbers. Pick a base unit (mm is conventional in Kerf) and stick
  with it across the project.
- A row that errors leaves its previous resolved value in scope
  (so downstream rows don't all cascade to NaN). The editor flags
  the bad row in red.
- Circular references (`a` references `b`, `b` references `a`)
  resolve to `NaN`. The evaluator shows the offending row.
- The `.equations` file is plain JSON — no comments. Use the
  per-row `"comment"` field instead.
