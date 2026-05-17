# Jewelry workflow

End-to-end guide: stone selection → setting → ring shank → weight/cost →
casting export → appraisal.

All jewelry logic lives in
`packages/kerf-cad-core/src/kerf_cad_core/jewelry/`. The modules are pure
Python and are called by the server-side OCCT worker ops; the LLM dispatches
them via the feature tool surface (`feature_pad`, `feature_pocket`, etc.) and
dedicated jewelry tools.

---

## 1. Start a jewelry project

Create a project with the `blank` or `jscad` starter:

```
POST /api/projects
{ "workspace_id": "…", "name": "Engagement ring", "starter": "blank" }
```

For rapid sketching, start with a `.jscad` script using `@jscad/modeling`
primitives, then migrate to `.feature` files once you need real B-rep (fillets,
STEP export, accurate weight).

---

## 2. Select a gemstone

The `jewelry/gemstones.py` module provides `build_gemstone(cut, size_mm,
color_code)` which returns a validated `Body` representing the stone in its
girdle reference frame.

Supported cuts include `round_brilliant`, `princess`, `cushion`, `emerald`,
`oval`, `pear`, `marquise`, `radiant`, `asscher`, `heart`, and the full
extended catalog from `gem_studio.py` (including coloured-stone variants with
correct refractive index / birefringence for sapphire, ruby, emerald, etc.).

The LLM can scaffold a gemstone feature via:

```
search_kerf_docs("gemstone")
→ read /docs/llm/jewelry/gemstone.md
→ edit_file the .feature to add a gemstone node
```

Key parameters: `cut`, `size_mm` (girdle diameter for round; length×width for
fancies), `depth_pct` (depth as % of diameter, defaults to GIA averages),
`color`, `clarity`.

---

## 3. Design the setting

Settings are in `jewelry/settings.py` and the extended `jewelry/head_wizard.py`
/ `jewelry/pave_wizard.py`. Types:

| Setting | Module | Description |
|---------|--------|-------------|
| Prong | `settings.py` | Round or claw prongs; 4 or 6 count |
| Bezel | `settings.py` | Full or half bezel wrapping the girdle |
| Channel | `settings.py` | Row of stones in a channel |
| Pavé | `pave_wizard.py` | Grid of micro-stones set in pavé holes |
| Head wizard | `head_wizard.py` | Parametric head library (cathedral, tapered, basket) |
| Bezel auto | `bezel_auto.py` | Auto-size bezel to stone girdle |
| Eternity auto | `eternity_auto.py` | Even stone spacing around a full band |
| Gallery | `gallery.py` | Under-gallery openwork patterns |

**Parametric DAG**: settings reference the gemstone by its `face:girdle`
persistent face ID. Change the stone size and the setting walls re-adjust
automatically via the `FeatureDAG` in
`kerf_cad_core.geom.history.dag.FeatureDAG`. The `regenerate()` call
re-evaluates only the invalidated nodes in topological order.

The LLM workflow:

```
search_kerf_docs("bezel setting")
→ read_file the .feature to see current stone node
→ edit_file to append a { "type": "bezel", "stone_ref": "gem_0", "wall_mm": 0.8 } node
```

---

## 4. Build the ring shank

The `jewelry/ring.py` module provides:

- `build_ring_shank(inner_diameter_mm, width_mm, depth_mm, profile)` —
  produces a `Body` with the shank cross-section swept along the ring circle.
- `ring_sizer(finger_size, standard)` — converts ISO/US/UK/JP ring sizes to
  inner diameter in mm.
- Shoulder variants: tapered, knife-edge, flat, comfort fit.

Extended shank types in `jewelry/profile_lib.py`: square, D-section, flat,
oval, and free-form spline.

Ring styles added in the v3/v4 builders (`jewelry/ring.py`):

- Eternity band
- Signet with flat bezel (engravable area via `jewelry/engraving.py`)
- Stacking ring (minimal depth, for multi-ring wear)
- Contoured band (follows finger curve)
- Composite builders in v4: split-shank, bypass, tension settings

**Parametric shank tip**: drive the shank inner diameter from a project
equation (`set_equation "finger_size_mm" = 17.35`). The ring shank node reads
`{inner_diameter: "$finger_size_mm"}` so changing the equation re-evaluates
the whole ring without breaking the fillet on the shank shoulder.

---

## 5. Metal weight and casting cost

`jewelry/metal_cost.py` provides:

```python
calculate_metal_weight(volume_cm3, metal) -> dict
    # {"weight_g": float, "metal": str}

calculate_casting_cost(weight_g, metal, quantity, region) -> dict
    # {"unit_cost_usd": float, "total_cost_usd": float, ...}
```

`jewelry/tool_metal_cost.py` exposes this as an LLM tool (`metal_cost`). The
tool is also surfaced via the REST endpoint:

```
POST /api/projects/{pid}/jewelry/metal-cost
{ "volume_cm3": 1.42, "metal": "18k_yellow_gold", "quantity": 10 }
```

Supported metals: `sterling_silver`, `9k/14k/18k/22k_yellow_gold`,
`18k_white_gold`, `18k_rose_gold`, `platinum_950`, `palladium_500`.

---

## 6. Costing and quoting

`jewelry/appraisal.py` assembles the full piece quote:

```python
appraise_piece(
    metal_weight_g, metal,
    stones: list[StoneSpec],
    labour_hours, region,
    markup_pct,
) -> AppraisalReport
```

Returns stone value, metal value, labour, overhead, and retail price.
`jewelry/production.py` adds production routing: wax carving (`cam_wax.py`),
direct casting (`casting_export.py`), or 3D-print presets (`print_presets.py`).

The appraisal tool (`search_kerf_docs("appraisal jewelry")`) documents the
full report schema.

---

## 7. Casting export

`jewelry/casting_export.py` provides:

```python
export_casting_stl(body, output_path, tolerance_mm)
export_wax_model(body, output_path)
```

For direct-metal laser sintering (DMLS) or resin printing:
`jewelry/print_presets.py` adjusts wall thickness, support angle, and
orientation based on the chosen material.

The LLM workflow:

```
search_kerf_docs("casting export jewelry")
→ read_file the .feature to get the final body node ID
→ call the export tool with the output path and tolerance
```

The resulting STL/OBJ is stored as a derived artifact on the file:

```
POST /api/projects/{pid}/files/{fid}/derived
{ "kind": "casting_stl", "tolerance_mm": 0.05 }
```

---

## 8. QC and tech drawing

`jewelry/cad_qc.py` runs geometric checks (wall thickness, prong count vs.
stone weight, bezel closure). `jewelry/tech_drawing.py` generates a
dimensioned 2D technical drawing of the ring suitable for bench jewellers.

`jewelry/setter_checklist.py` produces a stone-setter checklist (stone sizes,
seat depths, prong lengths).

---

## Module map

| Module | Purpose |
|--------|---------|
| `gemstones.py` | Stone solid + GIA-accurate cut geometry |
| `gem_studio.py` | Extended gem catalog + coloured-stone variants |
| `gem_seat.py` | Seat boolean (girdle recess in the setting) |
| `gem_cert.py` | Gem grading report schema |
| `settings.py` | Prong / bezel / channel / pavé |
| `pave_wizard.py` | Pavé hole grid generator |
| `head_wizard.py` | Parametric head / basket library |
| `bezel_auto.py` | Auto-sizing bezel |
| `eternity_auto.py` | Eternity band stone placement |
| `gallery.py` | Under-gallery openwork |
| `ring.py` | Ring shank + sizer + shoulder types (v1–v4) |
| `profile_lib.py` | Shank cross-section profiles |
| `family_ring.py` | Family-ring multi-ring builders |
| `chain.py` | Chain link geometry (multiple link styles) |
| `stringing.py` | Necklace / bracelet stringing |
| `findings.py` | Clasps, bails, jump rings |
| `bangle.py` | Bangle geometry |
| `filigree_advanced.py` | Filigree pattern generator |
| `decorative.py` | Milgrain, engraving borders |
| `engraving.py` | Text/pattern engraving on flat faces |
| `enamel.py` | Cloisonné cell geometry |
| `plating.py` | Plating cost and coverage estimation |
| `hollowing.py` | Shell-hollow for weight reduction |
| `repair.py` | Crack-detection and repair advice |
| `bas_relief.py` | Bas-relief embossing from height maps |
| `watch.py` | Watch-case geometry utilities |
| `mount_finder.py` | Best-fit setting finder for a given stone |
| `metal_cost.py` | Weight → cost calculation |
| `tool_metal_cost.py` | LLM tool wrapper for metal_cost |
| `appraisal.py` | Full piece appraisal report |
| `production.py` | Production routing (wax / cast / print) |
| `casting_export.py` | STL / OBJ export for casting |
| `wax_carving.py` | Wax milling toolpath strategy |
| `cam_wax.py` | CAM wax strategy wrapper |
| `print_presets.py` | 3D-print presets by material |
| `tech_drawing.py` | 2D technical drawing generator |
| `cad_qc.py` | Geometric QC checks |
| `setter_checklist.py` | Stone-setter preparation checklist |
| `templates.py` | Preset library (solitaire, halo, tennis, etc.) |
| `pieces.py` | High-level piece assembler |

---

See also: [parametric.md](./parametric.md) · [drawings.md](./drawings.md) · [llm-tools.md](./llm-tools.md) · [render-pipeline.md](./render-pipeline.md)
