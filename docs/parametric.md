# Parametric Design Stack

Kerf has three distinct parametric layers, each with a different scope and use case.

---

## 1. The Three Layers

### `.equations` — scalar parameters

Project-wide numeric variables evaluated via [mathjs](https://mathjs.org/). One `.equations` file feeds every file in a project. Expressions can reference each other in declaration order.

```json
{
  "version": 1,
  "params": [
    { "name": "wall_thickness", "expr": "2",              "unit": "mm", "comment": "Default wall" },
    { "name": "height",        "expr": "wall_thickness * 5", "unit": "mm" }
  ]
}
```

Schema: `packages/kerf-chat/llm_docs/equations.md`

### `.feature` — sequential feature tree

An ordered list of OCCT B-rep operations (pad, pocket, revolve, fillet, shell…). Fields use `${name}` placeholders that resolve to equations values at eval time.

```json
{
  "version": 1,
  "features": [
    { "id": "pad-1", "op": "pad", "sketch_path": "/profile.sketch",
      "height": "${height}", "direction": "up" }
  ]
}
```

Schema: `packages/kerf-chat/llm_docs/feature.md`

### `.graph` — node-based pipeline

A Grasshopper-equivalent DAG of nodes. Built-in ops (sliders, series, expressions, map_each) drive Kerf tool ops (feature_revolve, sketch_offset, etc.) via `@nX.out` references.

```jsonc
{
  "version": 1,
  "nodes": [
    { "id": "n1", "op": "number_slider", "params": { "value": 50 }, "inputs": [] },
    { "id": "n2", "op": "expression", "params": { "expr": "PI * @n1.out", "inputs": {} }, "inputs": ["n1"] }
  ],
  "outputs": ["n2"]
}
```

Schema: `packages/kerf-imports/llm_docs/graph.md`

---

## 2. When to Use Each

| Layer | Best for |
|-------|----------|
| `.equations` | Single variable drives many features — wall thickness, screw pitch, panel height |
| `.feature` | Sequential ops on one body — pad → pocket → fillet → shell |
| `.graph` | Complex pipelines, generative design, design exploration — multi-branch flows, iteration, sweeping series of features |

`.equations` and `.feature` are composable: equations feeds feature placeholders. `.graph` is the highest-level layer — it can invoke feature ops as nodes.

For per-variant parameter overrides (M3/M4/M5 sizes, engraved vs blank), see [configurations](#cross-references) below.

---

## 3. Worked Example: Parametric Box

### Step 1 — Equations

```json
{
  "version": 1,
  "params": [
    { "name": "width",          "expr": "60",  "unit": "mm" },
    { "name": "height",         "expr": "40",  "unit": "mm" },
    { "name": "depth",          "expr": "30",  "unit": "mm" },
    { "name": "wall_thickness", "expr": "2",   "unit": "mm" }
  ]
}
```

### Step 2 — Feature tree

Assumes `/box-profile.sketch` (60×40 rect) and `/inner-profile.sketch` (56×36 rect) exist.

```json
{
  "version": 1,
  "name": "Parametric box",
  "features": [
    {
      "id": "outer-pad",
      "op": "pad",
      "sketch_path": "/box-profile.sketch",
      "height": "${depth}",
      "direction": "up"
    },
    {
      "id": "inner-pocket",
      "op": "pocket",
      "target_id": "outer-pad",
      "sketch_path": "/inner-profile.sketch",
      "depth": "${depth - wall_thickness}"
    },
    {
      "id": "top-shell",
      "op": "shell",
      "target_id": "inner-pocket",
      "thickness": "${wall_thickness}",
      "face_ids": []
    }
  ]
}
```

Changing `wall_thickness` in the equations file adjusts the pocket depth and shell thickness simultaneously.

---

## 4. Worked Example: Parametric Pulley

A timing pulley driven by a diameter slider. The graph produces N tooth positions via `series`, computes circumference via `expression`, then sweeps a tooth profile around the axis.

```jsonc
{
  "version": 1,
  "name": "Parametric pulley",
  "nodes": [
    { "id": "n1", "op": "integer_slider",
      "params": { "min": 8, "max": 48, "value": 20, "step": 1 },
      "inputs": [] },

    { "id": "n2", "op": "expression",
      "params": { "expr": "PI * d / N", "inputs": { "d": 40, "N": "@n1.out" } },
      "inputs": ["n1"] },

    { "id": "n3", "op": "series",
      "params": { "start": 0, "count": "@n1.out", "step": 1 },
      "inputs": ["n1"] },

    { "id": "n4", "op": "feature_revolve",
      "params": {
        "sketch_path": "/pulley-tooth.sketch",
        "axis": "z",
        "angle_deg": 360
      },
      "inputs": ["n3"] }
  ],
  "outputs": ["n4"]
}
```

The `series` node emits `[0, 1, 2, …, N-1]` which the `feature_revolve` uses to distribute teeth evenly around the axis.

---

## 5. Cross-References

**Configurations / variants** — per-file parameter overrides for producing multiple flavors (M3/M4/M5, long/short, engraved/blank) from a single source file. Config params merge *over* the equations scope at eval time.

```
.equations  →  .feature  →  .graph
     ↑               ↑
     └── configs override equations scope
```

Schema: `packages/kerf-chat/llm_docs/configurations.md`
