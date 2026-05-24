# Architectural Drafting — LLM Reference

2D hatch fills, section fills, and hidden-line projections.

## Tool: `bim_hatch_region`

Fill a closed 2D planar region with an architectural hatch pattern.

```json
{
  "boundary": [[0,0,0],[4000,0,0],[4000,3000,0],[0,3000,0]],
  "pattern": "brick",
  "angle": 0,
  "scale": 200
}
```

### Supported patterns

| key | description |
|-----|-------------|
| `ansi31` | General 45° hatching (default) |
| `concrete` | Concrete aggregate fill |
| `brick` | Brick course pattern |
| `earth` | Earth / soil fill |
| `wood` | Wood grain |
| `sand` | Sand fill |
| `insulation` | Insulation batting |
| `steel` | Steel crosshatch |
| `glass` | Glass diagonal |

---

## Tool: `bim_section_fill`

Section a triangle mesh with a plane and fill resulting loops with hatch.

```json
{
  "vertices": [[0,0,0],[1,0,0],[1,1,0],[0,1,0],[0.5,0.5,1]],
  "triangles": [[0,1,4],[1,2,4],[2,3,4],[3,0,4]],
  "plane_normal": [0,1,0],
  "plane_point": [0,0.5,0],
  "material": "brick_clay"
}
```

Pass `material` (e.g. `"brick_clay"`, `"concrete"`, `"steel"`) to derive the
hatch pattern automatically.  Use `pattern` for explicit override.

---

## Tool: `bim_make2d_from_brep`

Project a 3D mesh to 2D with hidden-line removal.

```json
{
  "vertices": [[0,0,0],[1,0,0],[1,1,0],[0,1,0],[0,0,1],[1,0,1],[1,1,1],[0,1,1]],
  "triangles": [[0,1,2],[0,2,3],[4,5,6],[4,6,7],...],
  "view_direction": [-1,-1,-1],
  "scale": 1.0
}
```

Returns `visible` (solid) and `hidden` (dashed) 2D polyline lists.
