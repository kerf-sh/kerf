# Authoring `.topo` files

A `.topo` file is a SIMP (Solid Isotropic Material with Penalization)
topology-optimization specification attached to a `.feature` design space.
It records the volume fraction target, penalization power, filter radius,
maximum iterations, and convergence tolerance. The Topo tab
(`src/components/TopoView.jsx`) reads it; the Run button submits the job
to the pyworker FEniCSx engine.

## File shape

```json
{
  "version": 1,
  "design_space_feature_path": "/bracket.feature",
  "material_path": "/library/aisi-1018.material",
  "volume_fraction": 0.3,
  "penalization_power": 3,
  "filter_radius_mm": 1.5,
  "max_iterations": 200,
  "convergence_tolerance": 1e-4,
  "results": {
    "status": "pending",
    "iterations": 0,
    "final_compliance": null,
    "final_volume_fraction": null,
    "warnings": [],
    "errors": [],
    "output_mesh_file_id": null
  }
}
```

- `version` must be `1`. Anything else renders as "unsupported".
- `design_space_feature_path` is the absolute path of the `.feature` file
  that defines the design domain (the solid body to optimize).
- `material_path` is the absolute path of the `.material` file providing
  E, ν, ρ needed by the FEM stiffness solve.
- `volume_fraction` is the target fraction of original material remaining
  (0 < V_f < 1; industry default is 0.3–0.5).
- `penalization_power` is the SIMP exponent p (industry standard p = 3).
- `filter_radius_mm` is the Heaviside filter kernel radius in mm.
- `max_iterations` caps the SIMP loop; the engine stops early on KKT
  convergence.
- `convergence_tolerance` is the relative change in compliance below which
  the loop terminates.
- `results` is populated by the engine after a Run; until then it shows
  `"pending"`.

## SIMP algorithm (FEniCSx)

The pyworker `POST /run-topo` route executes this loop server-side:

```
1.  Load design-space mesh from the .feature geometry.
2.  Initialize ρᵢ = V_target everywhere in the design domain.
3.  Repeat (for i = 1 … max_iterations):
      a.  Compute element stiffness K_e = ρᵢᵖ · K_solid (SIMP interpolation).
      b.  Assemble global K = Σ K_e.
      c.  Solve K · u = F  (Dirichlet on fixed faces, load on load faces).
      d.  Compute compliance C = Fᵀ · u.
      e.  Compute sensitivity ∂C/∂ρᵢ using the adjoint method:
              ∂C/∂ρ = −p · ρ^(p−1) · uᵀ · K_solid · u
      f.  Apply Heaviside filter to sensitivities:
              ∂Ĉ/∂ρ = (Σ w_j · ρ_j · |∂C/∂ρ_j|) / (Σ w_j · ρ_j)
              where w_j = max(0, R − |x_i − x_j|)  (cylinder filter)
      g.  Optimality Criteria (OC) update:
              if ∂C/∂ρ < 0:  ρ_new = ρ · (−∂C/∂ρ / (λ · V_target))^move
              if ∂C/∂ρ > 0:  ρ_new = ρ · (−∂C/∂ρ / (λ · V_target))^move
              λ is found by bisection to satisfy Σ ρ_new = V · V_target
              move = 0.2  (move limit for stability)
              ρ_new = clamp(ρ_new, ρ_min=0.001, ρ_max=1.0)
      h.  Apply Heaviside projection to push intermediate densities:
              ρ_proj = tanh(β · ρ) / tanh(β)   (β = 5…20, grows each iteration)
      i.  Check convergence:
              if |C_new − C_old| / C_old < tolerance: break
3.  Run marching-cubes at ρ_threshold = 0.5 on the final density field.
4.  Save the binary mesh as a new `.step` artifact file.
5.  Return { output_file_id, final_compliance, final_volume_fraction, iterations }.
```

## Common edits

### Increase penalization to push binary result

```text
old: "penalization_power": 3,
new: "penalization_power": 4,
```

### Tighten convergence for fine results

```text
old: "convergence_tolerance": 1e-4,
new: "convergence_tolerance": 1e-5,
```

### Reduce material usage (lighter part)

```text
old: "volume_fraction": 0.3,
new: "volume_fraction": 0.2,
```

### Increase filter radius for smoother result

```text
old: "filter_radius_mm": 1.5,
new: "filter_radius_mm": 2.5,
```

## Engine-pending convention

When the user clicks Run before the FEniCSx engine is wired, the
pyworker appends the sentinel:

```
Engine pending — FEniCSx not yet deployed.
```

to `results.warnings` (idempotent) and writes back the file. The
TopoView uses this to render an "engine pending" banner.

## Known limits

- **No FEniCSx engine yet.** `results.warnings` stays empty and
  `results.output_mesh_file_id` stays null; the TopoView shows the
  engine-pending banner. The `.topo` file shape is correct so the UI
  can be built ahead of the engine.
- **One design space per topo.** No multi-body optimization yet.
- **Fixed faces / loads** are inferred from the .feature's
  `boundary_conditions` metadata field (TBD schema). Until that schema
  lands, the stub Run uses placeholder BCs.