# Surface Boolean Robustness Layer

Pure-Python guards for dense-NURBS surface boolean operations
(`kerf_cad_core.geom.surface_boolean_robust`). No OCC dependency.

This module wraps any OCC boolean back-end with: input health-checking,
automatic bbox-relative tolerance scaling, and a single retry with relaxed
tolerance. It is the pre-flight layer called internally by `feature_surface_boolean`
before invoking the OCCT worker. Use it directly from `.script.py` when
implementing custom surface boolean pipelines.

---

## When to use (developer / script context)

Use these functions when you need to:

- validate a `NurbsSurface` for boolean suitability before sending to OCC
  (`surface_health_check`)
- run a robust boolean that auto-scales tolerance and retries on failure
  (`surface_boolean_robust`)
- diagnose why a surface boolean is failing (degenerate patches,
  self-intersecting control nets, duplicate control points, high degree)
- test your OCC boolean implementation without an OCC installation (pass
  `occ_fn=None` to get guards-only mode)

For project-level surface booleans, use `feature_surface_boolean` (documented
in `surfacing.md`) — it routes through this layer automatically.

---

## Functions

### `surface_health_check(srf)`

Validate a `NurbsSurface` for boolean suitability. Returns:

```python
{
    "ok": bool,
    "warnings": list[str],   # non-fatal (boolean may proceed with caution)
    "errors": list[str],     # fatal (boolean will be rejected)
}
```

Checks performed:
1. **Type guard** — must be a `NurbsSurface` instance.
2. **Degenerate patches** — near-zero-area control-net quads (cross-product of
   diagonals). ≥ 50% degenerate → `error`; any degenerate → `warning`.
3. **Self-intersecting control net** — sign-flip in consecutive cross-products
   of row-span vectors (heuristic, catches folded/twisted nets). → `error`.
4. **Duplicate consecutive control points** → `warning`.
5. **Degree sanity** — degree < 1 → `error`; degree > 9 → `warning` (numerically
   unstable for booleans).

---

### `surface_boolean_robust(srf_a, srf_b, kind, *, bbox_tol=None, occ_fn=None)`

Robust wrapper for a surface boolean. `kind` must be `"cut"`, `"fuse"`, or
`"common"`. Returns:

```python
{
    "ok": bool,
    "result": Any,         # occ_fn return value on success, else None
    "reason": str,         # failure description (empty on success)
    "retried": bool,       # True if first attempt failed and retry succeeded
    "tolerance": float,    # tolerance actually used
    "health_a": dict,      # surface_health_check result for srf_a
    "health_b": dict,      # surface_health_check result for srf_b
}
```

**Guards applied (in order):**
1. `kind` validation.
2. `surface_health_check` on both surfaces — rejects immediately on any `error`.
3. Tolerance auto-scaling: `tol = bbox_diagonal × 1e-4`, clamped to `[1e-7, 1e-2]`.
   Override via `bbox_tol`.
4. First call to `occ_fn(srf_a, srf_b, kind, tol)`.
5. If first call fails or returns `None`: retry with `tol × 10` (if still within
   `1e-2` ceiling).
6. Never raises — all exceptions are caught and surfaced in `reason`.

**Guards-only mode:** pass `occ_fn=None` to run all checks without any OCC call.
Useful for unit tests.

**Parameters:**
- `srf_a`, `srf_b` — `NurbsSurface` operands
- `kind` — `"cut"`, `"fuse"`, or `"common"`
- `bbox_tol` — override auto-computed tolerance (positive float)
- `occ_fn` — callable `(srf_a, srf_b, kind, tol) → result` (or `None`)

---

## Example

**Script context — health-check a surface before a custom boolean:**

```python
from kerf_cad_core.geom.surface_boolean_robust import (
    surface_health_check,
    surface_boolean_robust,
)

h = surface_health_check(my_nurbs_surface)
if not h["ok"]:
    print("Cannot boolean:", h["errors"])
else:
    if h["warnings"]:
        print("Warnings:", h["warnings"])
    result = surface_boolean_robust(
        my_nurbs_surface, cutter_surface, "cut",
        occ_fn=my_occ_cut_function,
    )
    if not result["ok"]:
        print("Boolean failed:", result["reason"])
        print("Retried:", result["retried"])
```

---

## Constants

| Name | Value | Meaning |
|---|---|---|
| `_TOL_MIN` | `1e-7` | Minimum allowed tolerance |
| `_TOL_MAX` | `1e-2` | Maximum allowed tolerance |
| `_TOL_FRACTION` | `1e-4` | bbox-diagonal fraction for auto-tol |
| `_TOL_RELAX_FACTOR` | `10.0` | Retry tolerance multiplier |

---

## Notes

- All functions are **pure-Python** (numpy only); no OCC required.
- The health check is a necessary but not sufficient pre-filter — it eliminates
  obvious degenerate inputs but cannot guarantee a clean OCC boolean result.
- For project-level surface booleans use `feature_surface_boolean`; it already
  calls this layer internally with the correct `occ_fn`.
- The retry logic is one-shot; if two retries are needed, the surface geometry
  is likely too degenerate for robust booleans — consider degree reduction or
  knot removal first.
