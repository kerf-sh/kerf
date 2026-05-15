# `feature_quad_remesh` — quad-dominant remeshing via Instant Meshes

Remeshes a triangle mesh into a **quad-dominant** topology using
[Instant Meshes](https://github.com/wjakob/instant-meshes) (MIT licence).
The output is a `.quadmesh` file containing vertices, quad faces, residual
triangle faces, and processing statistics.

Quad topology is required for Catmull-Clark subdivision (SubD prep),
improves element quality in structured FEM, and is the standard retopology
workflow for organic shapes.

## Schema

```json
{
  "id": "quad-remesh-1",
  "op": "quad_remesh",
  "target_feature_ref": "pad-1",
  "target_vertex_count": 5000,
  "crease_angle_deg": 20,
  "align_to_boundary": true,
  "smoothness_iters": 2
}
```

### Parameters

| Parameter             | Type    | Required | Default | Notes                                                        |
|-----------------------|---------|----------|---------|--------------------------------------------------------------|
| `file_id`             | string  | ✅       | —       | UUID of the `.feature` file to operate on                    |
| `target_feature_ref`  | string  | ✅       | —       | Node id of the source mesh / solid (e.g. `"pad-1"`)          |
| `target_vertex_count` | integer | —        | 5000    | Approximate output vertex count; IM may produce ±20%         |
| `crease_angle_deg`    | number  | —        | 20      | Dihedral threshold for sharp creases (stored on node)        |
| `align_to_boundary`   | boolean | —        | true    | Pass `--boundaries` to Instant Meshes                        |
| `smoothness_iters`    | integer | —        | 2       | Smoothing iterations (0–6); higher = more regular faces      |

## Output `.quadmesh` file

```json
{
  "vertices":  [[x, y, z], ...],
  "quads":     [[a, b, c, d], ...],
  "triangles": [[a, b, c], ...],
  "stats": {
    "vertex_count": 4987,
    "quad_count":   4812,
    "tri_count":    24,
    "elapsed_s":    3.14,
    "target_verts": 5000,
    "smoothness":   2,
    "align_boundary": true
  }
}
```

All face indices are 0-based.  Instant Meshes produces predominantly quad
faces with a small number of residual triangles at poles and irregular
regions.

## Sample stats

```
vertex_count  4 987
quad_count    4 812   (97%)
tri_count        24   (0.5%)
elapsed_s       3.14 s
```

## Graceful degradation

The `instant-meshes` binary is **optional**.  When it is absent:

- The LLM tool returns `{ "status": "binary_missing", "warning": "...", "hint": "..." }`
  so the chat agent can surface a friendly install message.
- `POST /run-quad-remesh` returns **HTTP 503** with a message pointing to
  https://github.com/wjakob/instant-meshes/releases.
- The `.quadmesh` file kind, `QuadMeshView`, and `FeatureView` inspector
  entry are always available — you can store and view previously computed
  meshes without the binary installed.

## Install hint

Pre-built binaries for macOS, Linux, and Windows are available at
https://github.com/wjakob/instant-meshes/releases.

Place the binary somewhere on `PATH` as `instant-meshes`.

Homebrew (unofficial tap):
```bash
brew install wjakob/instant-meshes/instant-meshes
```

Or build from source (requires CMake + OpenGL):
```bash
git clone --recursive https://github.com/wjakob/instant-meshes
cd instant-meshes && mkdir build && cd build
cmake .. && make -j$(nproc)
```

## HTTP route

```
POST /run-quad-remesh
Content-Type: application/json

{
  "obj_b64":             "<base64-encoded OBJ>",
  "target_vertex_count": 5000,
  "smoothness_iters":    2,
  "align_to_boundary":   true
}
```

Returns the same structure as the `.quadmesh` file on success; HTTP 503
when the binary is absent.

## Notes

- Instant Meshes 1.0.x is targeted.  The `-v` (target vertices), `-s`
  (smoothing iterations), and `--boundaries` flags are used.
- Timeout: 30 seconds.  Reduce `target_vertex_count` or simplify the input
  mesh if the timeout is hit.
- The LLM tool uses a placeholder unit-cube OBJ when called without a
  pre-exported mesh so the registration/validation round-trip is always
  testable regardless of OCC availability.
- Full OCC → STL → OBJ export pipeline for production callers is the
  HTTP route path: base64-encode your OBJ and POST to `/run-quad-remesh`.
