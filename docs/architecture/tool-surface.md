# LLM Tool Surface Audit

_T-308 — Anchored at commit `6c8f54f` — 2026-05-19_

---

## Before: 80+ per-plugin tools

Every plugin registered its implementation functions directly into the LLM
tool registry (`ctx.tools.register` / `@register` decorator).  Every tool
spec shipped with every chat turn as system-prompt context.

### Count by package

| Package | Tools registered |
|---|---|
| kerf-api (file_ops, scaffold, object_ops, revisions, configurations, equations, validation, project_layers, material, assembly_management) | ~43 |
| kerf-fem | fem_run, fem_job_status, fem_nonlinear_bar, fem_truss_plastic, fem_nonlinear, fem_fatigue = 6 |
| kerf-cam | cam_run, cam_job_status, create_tool, update_tool, delete_tool, list_tools = 6 |
| kerf-render | create_render, set_render_camera, add_render_light, set_render_material_override, run_render = 5 |
| kerf-mates | add_mate, delete_mate, list_mates, solve_assembly, tolerance_auto_chain, add_joint, solve_joints, tolerance3d_analysis = 8 |
| kerf-motion | simulate_motion, solve_ik, compute_workspace = 3 |
| kerf-topo | topo_run = 1 |
| kerf-gdnt | gdnt_list_symbols, gdnt_create_fcf, gdnt_validate_fcf, gdnt_inspect_feature, gdnt_build_report = 5 |
| kerf-structural | structural_rc_beam, structural_steel_beam, structural_rebar, structural_loads = 4 |
| kerf-landscape | landscape_contours, landscape_cut_fill, landscape_runoff, landscape_plants, landscape_paver_pattern, landscape_retaining_wall = 6 |
| kerf-civil | civil_horizontal_alignment, civil_vertical_alignment, civil_corridor_sections, civil_earthwork_volume = 4 |
| kerf-piping | 3 |
| kerf-microfluidics | 4 |
| kerf-marine | 3 |
| kerf-optics | optics_trace_ray, optics_lens_design = 2 |
| kerf-dental | dental_crown_design, dental_surgical_guide, dental_dicom_ingest = 3 |
| kerf-1dsim | sim1d_run, sim1d_parse = 2 |
| kerf-apparel | apparel_grade_bodice, apparel_add_seam, apparel_make_marker = 3 |
| kerf-composites | layup_analysis = 1 |
| kerf-bim | variable (dynamic) |
| kerf-electronics | variable (dynamic) |
| kerf-hvac | variable (dynamic) |
| kerf-energy | variable (dynamic) |
| kerf-interior | variable (dynamic) |
| kerf-woodworking | variable (dynamic) |
| kerf-packaging | variable (dynamic) |
| kerf-chat | search_kerf_docs = 1 |
| kerf-firmware | build_firmware = 1 |
| kerf-plc | run_plc_lint, create_ladder_rung = 2 |
| kerf-slicing | run_print_slice = 1 |
| kerf-wiring | run_wireviz, route_harness_3d = 2 |
| **Minimum total** | **≈ 80** |

Every tool spec consumed system-prompt tokens on every chat turn.  Many specs
were also conditional load-time failure points (OCC, opencamlib, blender
import guards).

---

## After: 14-tool catalog  (T-308)

Defined in `packages/kerf-chat/src/kerf_chat/tools/catalog.py`.
Dispatched by `packages/kerf-chat/src/kerf_chat/tools/dispatcher.py`.

| # | Tool name | Replaces |
|---|---|---|
| 1 | `read_file(path)` | read_file |
| 2 | `write_file(path, content)` | write_file |
| 3 | `edit_file(path, old_string, new_string, replace_all=false)` | edit_file (+ new replace_all flag) |
| 4 | `list_files(glob=null)` | list_files (+ glob filter) |
| 5 | `search_files(pattern, glob=null)` | search_code (renamed, + glob filter) |
| 6 | `create_file(path, kind, options={})` | create_sketch + create_feature + create_part + create_circuit + create_file + create_drawing |
| 7 | `describe_part(path, part_id=null)` | *new* — read-only structured inspector |
| 8 | `search_kerf_docs(query)` | search_kerf_docs (unchanged) |
| 9 | `duplicate_object(path, object_id, new_id=null)` | duplicate_object (unchanged) |
| 10 | `delete_object(path, object_id)` | delete_object (unchanged) |
| 11 | `import_step(name, source_url, parent_path="/")` | import_step (renamed arg) |
| 12 | `export_artifact(file_id, format)` | *new* — unified export |
| 13 | `run_compute(engine, file_id, options={})` | cam_run + fem_run + topo_run + run_render + cfd + spice + tess |
| 14 | `poll_compute(job_id)` | cam_job_status + fem_job_status + … (routes by job_id prefix) |

**Total: 14 tools** (≤ 14 budget).

### Tools removed from LLM surface (implementations kept)

The following tools are **no longer advertised to the LLM**.  Their Python
implementations remain importable and callable server-side.  They were folded
into the catalog tools above or are domain-specific enough that the generic
tools + docs-search workflow is sufficient.

- All kerf-fem sub-tools (fem_nonlinear_bar, fem_truss_plastic, fem_nonlinear, fem_fatigue)
- All kerf-cam tool-DB tools (create_tool, update_tool, delete_tool, list_tools)
- All kerf-render scene tools (create_render, set_render_camera, add_render_light, set_render_material_override)
- All kerf-mates tools (add_mate, delete_mate, list_mates, solve_assembly, …)
- All kerf-motion tools
- All domain-vertical tools (gdnt_*, structural_*, landscape_*, civil_*, piping, microfluidics, marine, optics, dental, 1dsim, apparel, composites, bim, electronics, hvac, energy, interior, woodworking, packaging, firmware, plc, slicing, wiring)
- kerf-api secondary tools (revisions, configurations, equations, validation, project_layers, material, assembly_management)

---

## Cache-control behaviour (unchanged)

`AnthropicProvider.complete` in `packages/kerf-chat/src/kerf_chat/llm.py` still
attaches `cache_control: {type: ephemeral}` to the **last entry** in the tools
array.  With 14 tools instead of 80+, the breakpoint covers the entire tool
list, maximising cache hits.
