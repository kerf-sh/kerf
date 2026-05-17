# AFR — Automatic Feature Recognition

Re-parameterize an imported "dumb" B-rep into an ordered, editable feature tree using an
Attribute-Adjacency-Graph (AAG) algorithm.  Pure Python, no OCC dependency.  Never raises.

---

## When to use

Keywords: feature recognition, AFR, automatic feature recognition, dumb solid, imported
STEP, dumb CAD, reconstruct feature tree, editable features from mesh, machining features,
hole detection, pocket detection, boss detection, counterbore, countersink, fillet
recognition, chamfer recognition, rib, step, slot recognition.

---

## Entrypoints

### `recognize_features(topology) -> dict`

Main entry point.  Accepts a B-rep topology dict **or** a triangle-mesh cluster dict.

**B-rep topology input schema:**
```json
{
  "faces": [
    {
      "id": "<str|int>",
      "type": "planar|cylindrical|conical|spherical|toroidal|other",
      "normal": [nx, ny, nz],
      "radius": 0.0,
      "area": 0.0,
      "convexity": "convex|concave|flat",
      "adjacent": ["<face_id>", ...]
    }
  ],
  "edges": [
    {
      "id": "<str|int>",
      "face_a": "<face_id>",
      "face_b": "<face_id>",
      "convexity": "convex|concave|tangent",
      "length": 0.0
    }
  ]
}
```

**Mesh-cluster input schema** (alternative):
```json
{
  "vertices": [[x,y,z], ...],
  "triangles": [[i,j,k], ...],
  "face_clusters": [
    {
      "id": "<int>",
      "type": "planar|cylindrical|...",
      "normal": [nx,ny,nz],
      "radius": 0.0,
      "area": 0.0,
      "convexity": "convex|concave|flat",
      "adjacent": [<cluster_id>, ...]
    }
  ]
}
```

**Returns:**
```json
{
  "ok": true,
  "features": [
    {
      "type": "<feature_type>",
      "params": {},
      "face_ids": [],
      "confidence": 0.85
    }
  ],
  "feature_tree": [
    { "type": "<feature_type>", "index": 0 }
  ],
  "reason": "recognized 3 feature(s) from 12 face(s)"
}
```

Never raises — returns `{"ok": false, "features": [], "feature_tree": [], "reason": "<msg>"}` on error.

---

## Supported feature types

| Feature | Detection strategy | Confidence range |
|---|---|---|
| `through_hole` | Concave cylinder, no floor cap | 0.85–0.90 |
| `blind_hole` | Concave cylinder + 1 planar cap parallel to axis | 0.87 |
| `counterbore` | Two coaxial concave cylinders of different radii + shared step face | 0.82 |
| `countersink` | Conical face + optional coaxial inner cylinder | 0.80 |
| `pocket` | Concave closed face loop with planar floor | 0.78 |
| `slot` | Pocket whose floor bbox aspect ratio ≥ 3 | 0.75 |
| `boss` | Convex cylindrical protrusion above a base face | 0.80 |
| `fillet` | Toroidal face, or small-radius cylinder tangent to ≥2 planar neighbours | 0.82–0.90 |
| `chamfer` | Planar face whose normal is 30–60° to ≥2 adjacent face normals | 0.72 |
| `rib` | Convex planar face with ≥2 concave-edge neighbours | 0.65 |
| `step` | Pair of coplanar faces separated by a perpendicular riser | 0.70 |

Feature tree order: base → boss/rib (additive) → pocket/slot → holes → fillets → chamfers.

---

## LLM tool name

`afr_recognize_features` — registered in kerf_chat tool registry.  Accepts a `topology` dict.

---

## Usage snippets

```python
from kerf_cad_core.afr.recognize import recognize_features

topology = {
    "faces": [
        {"id": 0, "type": "planar", "normal": [0,0,1], "radius": 0, "area": 100,
         "convexity": "flat", "adjacent": [1,2,3,4]},
        {"id": 1, "type": "cylindrical", "normal": [0,0,1], "radius": 5, "area": 94.25,
         "convexity": "concave", "adjacent": [0]},
    ]
}
result = recognize_features(topology)
# result["features"][0]["type"] == "through_hole"
# result["features"][0]["params"]["diameter"] == 10.0
```

```python
# Mesh-cluster path (from a segmented STL)
topology = {
    "vertices": [...],
    "triangles": [...],
    "face_clusters": [
        {"id": 0, "type": "planar", "normal": [0,0,1], "radius": 0, "area": 200,
         "convexity": "flat", "adjacent": [1]},
        {"id": 1, "type": "cylindrical", "normal": [0,0,1], "radius": 8, "area": 150,
         "convexity": "concave", "adjacent": [0]},
    ]
}
result = recognize_features(topology)
```

---

## Caveats

- Confidence values are heuristic; counterbore detection requires the shared step face to be
  explicitly listed in both cylinders' `adjacent` lists.
- Slot vs pocket classification uses `face.bbox` (optional); falls back to area heuristic.
- Rib detection has the lowest confidence (0.65) — validate results before machining ops.
- `edges` list is optional but improves fillet/chamfer accuracy.

---

## References

Joshi & Chang (1988). "Graph-based heuristics for recognition of machined features from a 3D
solid model." *CAD* 20(2), 58–66.

Marefat & Kashyap (1990). "Geometric reasoning for recognition of 3D object features."
*IEEE PAMI* 12(10), 949–965.
