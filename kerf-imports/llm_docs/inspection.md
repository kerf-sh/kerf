# Inspection / Model Comparison

Compare two mesh files to compute geometric deviation, similar to FreeCAD's inspection tool.

## Tool: `compare_models`

```json
compare_models({
  file_id_a: "uuid-string",
  file_id_b: "uuid-string",
  tolerance_mm?: 0.1,   // tolerance threshold in mm
  sampling?: 1.0        // 0-1, reduce computation (default 1.0 = full)
})
```

### Returns

```json
{
  "ok": true,
  "data": {
    "summary": {
      "max_deviation": 0.25,
      "mean_deviation": 0.08,
      "percent_within_tolerance": 94.3
    },
    "deviations": [
      {"x": 0.0, "y": 0.0, "z": 0.0, "delta": 0.0},
      {"x": 1.0, "y": 0.0, "z": 0.0, "delta": 0.25}
    ]
  }
}
```

- `max_deviation`: Largest Euclidean distance found (mm)
- `mean_deviation`: Average distance across all sampled points
- `percent_within_tolerance`: % of points within the tolerance threshold
- `deviations`: Array of `{x, y, z, delta}` for each sampled vertex

## Workflow: Verify 3D-Printed Part vs Source Model

1. Upload the source model (STEP/mesh) to Kerf as file A
2. Upload the 3D-printed scan or mesh as file B
3. Call `compare_models` with both file IDs and tolerance (e.g., `0.1` mm)
4. Review:
   - `max_deviation > tolerance` → areas needing rework
   - `percent_within_tolerance < 100` → inspect specific deviation points
   - Use `deviations` array to find exact problem coordinates

## Example

```json
{
  "name": "compare_models",
  "arguments": {
    "file_id_a": "550e8400-e29b-41d4-a716-446655440000",
    "file_id_b": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
    "tolerance_mm": 0.1
  }
}
```