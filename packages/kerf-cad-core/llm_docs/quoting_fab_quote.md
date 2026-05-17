# quoting_fab_quote — One-Click Fabrication Quote Engine

Given a part's geometry summary (bounding-box, volume, surface area, feature inventory), determines viable manufacturing processes, estimates cost per process, recommends the best choice, and formats a quote report.

## When to use

Use these tools when an engineer or product designer needs to:
- Quickly determine which manufacturing process is most suitable for a part (CNC, casting, injection moulding, sheet metal, 3D printing, forging)
- Compare cost estimates across processes for a given quantity
- Get a recommended process based on cost, tolerance class, and lead-time trade-offs
- Generate a formatted fabrication quote summary for a chat response or report
- Assess process viability with blockers (e.g. "too many undercuts for die casting")

Keywords: fab quote, fabrication quote, manufacturing process, CNC, casting, injection moulding, sheet metal, 3D print, forging, process viability, unit cost, lead time, tolerance class, quantity, quote report.

## Processes analysed

| Process | Key viability heuristics |
|---|---|
| `cnc` | Suitable for most geometries; penalised for thin walls < 0.5 mm and high aspect-ratio pockets |
| `casting` | Preferred for complex geometry; blocked by very thin walls < 1 mm or excessive undercuts |
| `injection` | Suitable for high-volume plastics or zinc; requires draft angle ≥ 1°; blocked by no-draft faces |
| `sheet_metal` | Requires `is_flat_blank=true`; scored on bend count and blank size |
| `3d_print` | Always viable; cost rises steeply with volume and surface finish requirement |
| `forging` | Preferred when `requires_high_strength=true`; blocked by complex internal geometry |

## Tolerance class → process capability mapping

| Class | Typical Ra (µm) | IT grade |
|---|---|---|
| `coarse` | 25+ | IT12+ |
| `medium` | 6.3–12.5 | IT9–IT11 |
| `fine` | 1.6–3.2 | IT7–IT8 |
| `precision` | < 0.8 | IT6 or better |

## Part geometry summary schema

```
{
  "bbox_x": float,              // mm; bounding-box X
  "bbox_y": float,              // mm
  "bbox_z": float,              // mm
  "volume_cm3": float,          // cm³
  "surface_area_cm2": float,    // cm²
  "mass_kg": float,
  "num_holes": int,
  "num_threads": int,
  "num_undercuts": int,
  "thin_wall_count": int,
  "min_wall_mm": float,
  "draft_angle_deg": float,
  "is_flat_blank": bool,
  "num_bends": int,
  "complexity_score": float,    // 0–1; 0 = trivial
  "requires_high_strength": bool,
  "is_symmetric": bool,
  "tolerance_class": str,       // coarse | medium | fine | precision
  "finish_quality": str,        // rough | standard | fine | optical
  "material_cost_per_kg": float // USD
}
```

## Quote output fields

**Per process (from `cost_per_process`):**
```
{
  "process": str,
  "viability_score": float,     // 0–1
  "blockers": list[str],        // reasons this process cannot be used
  "advantages": list[str],
  "setup_cost_usd": float,
  "unit_material_cost_usd": float,
  "unit_machining_cost_usd": float,
  "unit_total_cost_usd": float,
  "lead_time_days": int,
}
```

## Tools

| Tool | Description |
|------|-------------|
| `fab_quote_analyze` | Read-only: parse geometry summary → `PartGeometry`; return viability scores, blockers, and advantages for all six processes; required: `geometry_summary` dict |
| `fab_quote_costs` | Read-only: compute per-process cost estimates for a given quantity; required: `geometry_summary`, `quantity` (int ≥ 1); optional `processes` list to restrict |
| `fab_quote_recommend` | Read-only: pick the best process from a cost list; returns `recommended_process`, `rationale`; required: `quotes` list from `fab_quote_costs` |
| `fab_quote_report` | Read-only: format a multi-line quote summary string; required: `geometry_summary`, `quotes`, `recommendation` |

## Example

Engineer: "Quote a 50 × 30 × 20 mm steel bracket, 1 000 units, fine tolerance, 2 M5 holes."

1. `fab_quote_analyze` — geometry_summary={bbox_x:50,bbox_y:30,bbox_z:20,volume_cm3:12,mass_kg:0.094,num_holes:2,num_threads:2,tolerance_class:"fine",material_cost_per_kg:2.5,...}
   → viability: cnc=0.92, casting=0.75, sheet_metal=blocked (not flat blank), 3d_print=0.60, forging=0.50
2. `fab_quote_costs` — geometry_summary=same, quantity=1000, processes=["cnc","casting","3d_print"]
   → sorted by unit cost: casting $2.40 < cnc $3.10 < 3d_print $8.20
3. `fab_quote_recommend` — quotes=`<from step 2>` → recommended=`casting`, rationale="lowest unit cost at fine tolerance for this volume"
4. `fab_quote_report` — format summary for the user
