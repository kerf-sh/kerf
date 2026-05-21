# Testing Breakdown Manifest — system-health phase

Single source of truth for the hardening pass. Subsequent sonnet agents pull one task
at a time, isolate it in a worktree, ship a green PR, mark the checkbox.

Ground rules for every task:

- Hermetic (no network, no external binaries). Mock SMTP, mock OCCT worker
  where unavoidable, mock outbound HTTP. Postgres tests must use the `pc`
  local role and an ephemeral schema/database per session.
- One commit per task: `test(<area>): <one-line summary>`.
- Minimum case counts below are floors — overshoot if the surface area
  warrants it. Cases should target real failure modes (boundaries,
  malformed input, idempotency, cross-tenant isolation), not just happy
  path.
- All test files live next to the package they exercise; new top-level
  pytest collections only when the parent package owns no test dir.

---

## Section 1 — Per-feature integration tests

Each task wires a *user-facing feature* end-to-end (chat → tool dispatch →
plugin call → worker / pure-python compute → render or export round-trip),
not a single internal module. ≥25 hermetic cases each unless otherwise
noted.

- [x] T-1 Jewelry: gemstone → seat → setting → ring composite
  Scope: gemstone catalog (`gemstones.py`) → `gem_seat.py` boolean → `settings.py` prong/bezel/channel/pavé → `ring.py` shank attach.
  File: `packages/kerf-cad-core/tests/test_feature_jewelry_ring_composite.py`
  Success: build 25 ring SKUs (stones × cuts × shank profiles), assert OCCT solid validity, mass-balance, gem clearance, no interpenetration.

- [x] T-2 Jewelry: eternity ring auto-distribution
  Scope: `eternity_auto.py` calibrated distribution end-to-end into a finished ring.
  File: `packages/kerf-cad-core/tests/test_feature_jewelry_eternity.py`
  Success: 25 size/stone/style permutations; expected stone count matches calibration table; total perimeter consumed = sum(seat widths) ± 0.05 mm.

- [x] T-3 Jewelry: bezel_auto wizard
  Scope: `bezel_auto.py` from arbitrary stone geometry through bezel/tube setting.
  File: `packages/kerf-cad-core/tests/test_feature_jewelry_bezel_auto.py`
  Success: 25 stone shapes (round/oval/marquise/pear/cushion/emerald + irregular cabochons); generated bezel wall thickness & seat depth within spec; clean boolean.

- [x] T-4 Jewelry: bangle / cuff / torque builders
  Scope: `bangle.py` parametric closure round-trip.
  File: `packages/kerf-cad-core/tests/test_feature_jewelry_bangle.py`
  Success: 25 wrist sizes × profile combinations; inner perimeter accuracy ±0.1 mm; hinge/clasp variants pass clash check.

- [x] T-5 Jewelry: chain / bracelet
  Scope: `chain.py` (curb, cable, byzantine, figaro, etc.), length sizing, clasp finding.
  File: `packages/kerf-cad-core/tests/test_feature_jewelry_chain.py`
  Success: 25 link styles × lengths; total length matches input ±1 link pitch; per-link non-intersection.

- [x] T-6 Jewelry: findings (clasps, jump rings, bails)
  Scope: `findings.py` library; round-trip into chains and earrings.
  File: `packages/kerf-cad-core/tests/test_feature_jewelry_findings.py`
  Success: 25 finding-attachment combos; correct wire gauge; female/male mate clearance.

- [x] T-7 Jewelry: profile library (cross-sections)
  Scope: `profile_lib.py` MatrixGold-parity profiles wired into `ring.py` shank.
  File: `packages/kerf-cad-core/tests/test_feature_jewelry_profile_lib.py`
  Success: 25 profile codes; centroid + section properties match analytic ground truth ±1%.

- [x] T-8 Jewelry: engraving / monogram / signet
  Scope: `engraving.py` stroke-font engrave onto signet face.
  File: `packages/kerf-cad-core/tests/test_feature_jewelry_engraving.py`
  Success: 25 text/glyph permutations; engraved depth & font fidelity; UTF-8 + ligature stress cases.

- [x] T-9 Jewelry: hollowing (weight reduction)
  Scope: `hollowing.py` shell with min-wall constraint.
  File: `packages/kerf-cad-core/tests/test_feature_jewelry_hollowing.py`
  Success: 25 part geometries; resulting solid has ≥ requested min wall everywhere; mass reduction within target ±3%.

- [x] T-10 Jewelry: pavé wizard (stone array on surface)
  Scope: `pave_wizard.py` end-to-end (surface → stone array → seat array → prong array).
  File: `packages/kerf-cad-core/tests/test_feature_jewelry_pave.py`
  Success: 25 host surfaces × stone sizes; stones tangent to surface within ε; no inter-stone clash; share-prong logic.

- [x] T-11 Jewelry: gallery / head wizard
  Scope: `gallery.py` + `head_wizard.py` composite head onto shank.
  File: `packages/kerf-cad-core/tests/test_feature_jewelry_head.py`
  Success: 25 head styles (4/6/8 prong, basket, cathedral, halo); attach point coincident with shank top.

- [x] T-12 Jewelry: casting / STL production export
  Scope: `casting_export.py` + `production.py` end-to-end STL/3MF.
  File: `packages/kerf-cad-core/tests/test_feature_jewelry_casting_export.py`
  Success: 25 finished SKUs; manifold STL; sprue/runner attachment; volume matches solid model ±0.5%.

- [x] T-13 Jewelry: metal cost / full quote
  Scope: `metal_cost.py` + `tool_metal_cost.py` quote against `pieces.py` BOM.
  File: `packages/kerf-cad-core/tests/test_feature_jewelry_cost_quote.py`
  Success: 25 SKUs × metal × spot prices; total = metal + casting + setting + finishing ±0.01; FX handling correct.

- [x] T-14 Jewelry: PBR materials (gem + metal)
  Scope: viewport material assignment + render hand-off (`packages/kerf-render` integration).
  File: `packages/kerf-render/tests/test_feature_jewelry_pbr.py`
  Success: 25 material assignments; correct dispersion / IOR / metal Fresnel parameters reach render payload.

- [x] T-15 Jewelry: gem report card
  Scope: `gem_studio.py` faceting → report (4 Cs, ASET, dispersion).
  File: `packages/kerf-cad-core/tests/test_feature_jewelry_gem_report.py`
  Success: 25 cuts × proportions; numerical 4Cs match catalog; light-return metric stable run-to-run.

- [x] T-16 Jewelry: preset / template library round-trip
  Scope: `templates.py` save / load / apply.
  File: `packages/kerf-cad-core/tests/test_feature_jewelry_templates.py`
  Success: 25 templates; deterministic re-instantiation; parameter migration on schema bump.

- [x] T-17 Mech: sheet-metal flange → unfold round-trip
  Scope: `sheet_metal.py` flange T-1 ⇒ unfold T-2/T-3 ⇒ flat pattern.
  File: `packages/kerf-cad-core/tests/test_feature_mech_sheet_metal_roundtrip.py`
  Success: 25 part shapes; folded area ≈ unfolded area within k-factor tolerance; bend allowance correct vs DIN 6935.

- [x] T-18 Mech: feature ops (boss-with-draft / cut-from-sketch / hole-pattern / loft / sweep / section)
  Scope: every feature_*.py file in `kerf-cad-core` root, chained.
  File: `packages/kerf-cad-core/tests/test_feature_mech_feature_ops_chain.py`
  Success: 25 5-op chains; face naming stable across rebuild; persistent IDs after boolean.

- [x] T-19 Mech: GD&T datum/tolerance framework
  Scope: `gdt/` + `gdt_callouts/` → drawing annotation surface.
  File: `packages/kerf-cad-core/tests/test_feature_mech_gdt.py`
  Success: 25 callout types (Y14.5); datum reference frames build correctly; round-trip into drawing JSON.

- [x] T-20 Mech: weldment profile library + cuts
  Scope: `weldment.py` + `weldment_profiles.py` (I-beam, channel, square tube) miter / cope cuts.
  File: `packages/kerf-cad-core/tests/test_feature_mech_weldment.py`
  Success: 25 frame layouts; member length, miter angle, cut volume vs analytic; weld seam topology.

- [x] T-21 Mech: thread features (cut + boss)
  Scope: `feature_thread.py` + `thread_specs.py` ISO/UNF/UNC.
  File: `packages/kerf-cad-core/tests/test_feature_mech_threads.py`
  Success: 25 thread specs; pitch/diameter match catalog; engagement length vs DIN/ASME.

- [x] T-22 Mech: assembly + mates
  Scope: `assembly/` plus `kerf-mates` `chain_walk.py` + `solver.py`.
  File: `packages/kerf-mates/tests/test_feature_mech_assembly_mates.py`
  Success: 25 assemblies (≥10 parts each); coincident/concentric/distance/angle mates resolve; over-/under-constrained detection.

- [x] T-23 Mech: fasteners library
  Scope: `fasteners/` ISO/DIN/ASME bolt + nut + washer generation.
  File: `packages/kerf-cad-core/tests/test_feature_mech_fasteners.py`
  Success: 25 fastener specs; dimensions match standard; hole-pattern integration.

- [x] T-24 Mech: family parts (configurations)
  Scope: `family/` parametric family table → resolved instance.
  File: `packages/kerf-cad-core/tests/test_feature_mech_family.py`
  Success: 25 family rows; deterministic resolution; equation propagation.

- [x] T-25 Mech: gears / gearbox composite
  Scope: `gears.py` + `gearbox/` + `wormbevel/` mesh.
  File: `packages/kerf-cad-core/tests/test_feature_mech_gears.py`
  Success: 25 gear pair specs; module / addendum / dedendum vs AGMA; mesh clash check.

- [x] T-26 Mech: bearings catalog → housing fit
  Scope: `bearings/` standard catalog + housing bore generation.
  File: `packages/kerf-cad-core/tests/test_feature_mech_bearings.py`
  Success: 25 bearing codes; ISO 286 fits H7/g6 etc.; lip / shoulder geometry.

- [x] T-27 Electronic: PCB DRC + Gerber/Excellon/PnP/IPC-2581
  Scope: `kerf-electronics/dfm/` + `fab/` complete fab-output stack.
  File: `packages/kerf-electronics/tests/test_feature_pcb_fab_output_roundtrip.py`
  Success: 25 boards (1–8 layers); DRC clean; Gerber RS-274X passes lint; Excellon drills coincident; IPC-2581 round-trips.

- [x] T-28 Electronic: routing — autoroute + push-shove + RF + pour + diffpair
  Scope: `freerouting/` + `routes_*` modules + `kerf-electronics/routes_autoroute.py`.
  File: `packages/kerf-electronics/tests/test_feature_pcb_routing_complete.py`
  Success: 25 boards (mixed digital + RF + diff-pair); 100% net completion; length matching ±2%; copper-pour DRC clean.

- [x] T-29 Electronic: SPICE simulation hand-off
  Scope: `routes_spice.py` + circuit → `.cir` → result parse.
  File: `packages/kerf-electronics/tests/test_feature_pcb_spice.py`
  Success: 25 analog circuits (RC, opamp, regulator, oscillator); DC op-point / AC sweep / transient match analytic.

- [x] T-30 Electronic: 3D board STEP export + IDF MCAD
  Scope: `fab/board_step.py` + `fab/` IDF.
  File: `packages/kerf-electronics/tests/test_feature_pcb_3d_step.py`
  Success: 25 boards; STEP solid valid; component placement matches PnP; IDF round-trip back to PCB.

- [x] T-31 Electronic: netlist + ERC depth
  Scope: full ERC pass + KiCad / EAGLE / Allegro netlist export.
  File: `packages/kerf-electronics/tests/test_feature_pcb_netlist_erc.py`
  Success: 25 schematics; ERC catches floating-input / power-conflict / multi-driver classes; netlist round-trip.

- [x] T-32 Electronic: footprint / symbol library management
  Scope: `kerf-electronics/tools/` library CRUD + version pinning.
  File: `packages/kerf-electronics/tests/test_feature_pcb_lib_mgmt.py`
  Success: 25 lib operations; symbol-footprint binding integrity; LCSC / Octopart manifest stub.

- [x] T-33 Electronic: panelization + testpoint / fixture
  Scope: panelize.py + testpoint.py + fixture generator.
  File: `packages/kerf-electronics/tests/test_feature_pcb_panel_fixture.py`
  Success: 25 panels (V-score + mouse-bite); bed-of-nails fixture clearances; gold-finger / fiducial placement.

- [x] T-34 Electronic: BOM variants
  Scope: assembly BOM with DNP / variant assignment.
  File: `packages/kerf-electronics/tests/test_feature_pcb_bom_variants.py`
  Success: 25 variant configurations; DNP filtering; cost roll-up against `kerf-parts` distributors.

- [x] T-35 Electronic: flex / rigid-flex stackup
  Scope: `flex/` + `stackup/` controlled-impedance solver.
  File: `packages/kerf-electronics/tests/test_feature_pcb_flex_stackup.py`
  Success: 25 stackups; Zo / Zdiff vs IPC-2141 ±5%; bend-radius rule.

- [x] T-36 CAM 3-axis: post + tool DB integration
  Scope: `kerf-cam/posts/` + `tool_db.py` chained with `cam_jobs`.
  File: `packages/kerf-cam/tests/test_feature_cam3_post_tooldb.py`
  Success: 25 toolpaths; valid G-code for fanuc/haas/mach3/grbl; tool-change blocks; feed/speed from DB.

- [x] T-37 CAM 5-axis: 3+2 indexed
  Scope: `kerf-cam/five_axis/` + `kerf-cad-core/fiveaxis/`.
  File: `packages/kerf-cam/tests/test_feature_cam5_3plus2.py`
  Success: 25 setups; indexed plane resolves; kinematic limits checked; G68.2 / RTCP outputs differ correctly.

- [x] T-38 CAM: layered (additive milling) flow
  Scope: `cam_layered.py`.
  File: `packages/kerf-cad-core/tests/test_feature_cam_layered.py`
  Success: 25 part shapes; layer count, step-down, scallop within target; collision check.

- [x] T-39 Slicing: 3D-print Tier 1
  Scope: `kerf-slicing/cura_runner.py` integration.
  File: `packages/kerf-slicing/tests/test_feature_print_slice.py`
  Success: 25 parts; gcode generated; layer time estimate; volume check (within ±2% of solid mesh).

- [x] T-40 FEM: linear static end-to-end
  Scope: `kerf-fem/calculix_utils.py` + `fenicsx_utils.py` + `nonlinear_bar.py`.
  File: `packages/kerf-fem/tests/test_feature_fem_linear_static.py`
  Success: 25 canonical problems (cantilever, plate, etc.); displacement / stress match analytic ±2%.

- [x] T-41 Sketcher v2 (constraint solver)
  Scope: `kerf-cad-core/geom/curve_toolkit.py` + frontend sketch ops chained server-side.
  File: `packages/kerf-cad-core/tests/test_feature_sketcher_v2.py`
  Success: 25 sketches (incl. over-/under-constrained); solver converges; DOF report.

- [x] T-42 Drawings: project / dimension / annotate
  Scope: drawing-kind file generation (projection.test.js parity server side).
  File: `packages/kerf-cad-core/tests/test_feature_drawings.py`
  Success: 25 part-drawing pairs; HLR / hidden-line correct; dimensions auto; section view.

- [x] T-43 NURBS Phase 2/3 surface ops
  Scope: `geom/blend_srf.py` + `patch_srf.py` + `network_srf.py` + `sweep1.py` + `sweep2.py` + `revolve_srf.py`.
  File: `packages/kerf-cad-core/tests/test_feature_nurbs_surface_ops_phase23.py`
  Success: 25 surface constructions; tangency continuity (G1) along join edges; CV count sanity.

- [x] T-44 NURBS Phase 4 — match_srf / unroll_srf / fillet / intersection
  Scope: `geom/match_srf.py` + `unroll_srf.py` + `surface_fillet.py` + `intersection.py`.
  File: `packages/kerf-cad-core/tests/test_feature_nurbs_phase4_ops.py`
  Success: 25 cases mixed across the four ops; G2 continuity for match_srf; developable detection for unroll_srf.

- [x] T-45 NURBS: trim-by-curve + surface boolean robust
  Scope: `geom/trim_curve.py` + `surface_boolean_robust.py`.
  File: `packages/kerf-cad-core/tests/test_feature_nurbs_trim_boolean.py`
  Success: 25 trim/boolean cases incl. near-tangent and degenerate; robust fallback paths exercised.

- [x] T-46 Mesh: SubD + quad remesh + mesh-repair + mesh-to-NURBS
  Scope: `geom/subd.py` + `quad_remesh.py` + `mesh_repair.py` + `mesh_to_nurbs.py`.
  File: `packages/kerf-cad-core/tests/test_feature_mesh_pipeline.py`
  Success: 25 input meshes (broken / non-manifold included); repaired manifold; quad-dominant remesh; auto-surface fits.

- [x] T-47 Persistent face naming (Phase 4)
  Scope: `face_name_registry.py` across boolean / pattern / mates / sweep.
  File: `packages/kerf-cad-core/tests/test_feature_face_name_stability_full.py`
  Success: 25 rebuild scenarios; names stable; rename-on-collision deterministic.

- [x] T-48 Imports: DXF + DWG + KiCad + FreeCAD + IFC + Rhino
  Scope: `kerf-imports/{dwg,dxf,freecad,kicad,kicad_library,rhino3dm_route}` + IFC import.
  File: `packages/kerf-imports/tests/test_feature_imports_roundtrip.py`
  Success: 25 fixture files covering all 6 importers; entity-count + bbox parity post-import.

- [x] T-49 BIM: IFC export Tier 1+2
  Scope: `kerf-bim/export_ifc/` + `import_ifc/` round-trip.
  File: `packages/kerf-bim/tests/test_feature_bim_ifc_roundtrip.py`
  Success: 25 IFC4 element families; round-trip preserves GlobalId, geometry, psets.

- [x] T-50 Architecture: spaces + primitives
  Scope: `arch/spaces.py` + `arch/primitives.py` end-to-end space program.
  File: `packages/kerf-cad-core/tests/test_feature_arch_spaces.py`
  Success: 25 building programs; area / volume tallies; room adjacency graph.

- [ ] T-51 Civil: alignment + earthwork + hydraulics
  Scope: `civil/alignment.py` + `earthwork.py` + `hydraulics.py`.
  File: `packages/kerf-cad-core/tests/test_feature_civil_alignment.py`
  Success: 25 highway / drainage scenarios; stationing, cut/fill volumes, Manning's-n flow match references ±2%.

- [ ] T-52 Scan: point-cloud fit
  Scope: `scan/fit.py` (plane/cyl/sphere/torus RANSAC).
  File: `packages/kerf-cad-core/tests/test_feature_scan_fit.py`
  Success: 25 synthetic clouds with noise; primitive recovery within ε; outlier rejection.

- [ ] T-53 PLC structured text (.plc.st)
  Scope: `kerf-plc/matiec_lint.py` + parse + transpile fixtures.
  File: `packages/kerf-plc/tests/test_feature_plc_st.py`
  Success: 25 ST programs; lint clean / dirty mix; IEC 61131-3 conformance subset.

- [ ] T-54 Wiring harness diagrams
  Scope: `kerf-wiring/wireviz_runner.py` end-to-end.
  File: `packages/kerf-wiring/tests/test_feature_wiring_harness.py`
  Success: 25 harness specs; SVG/JSON output; pinmap integrity vs source schematic.

- [ ] T-55 Parts ingest + partsgen
  Scope: `kerf-parts/seed.py` + `kerf-partsgen/generators/`.
  File: `packages/kerf-parts/tests/test_feature_parts_ingest_gen.py`
  Success: 25 part families (fasteners + connectors); manifest hash deterministic; auto-attribution present.

- [ ] T-56 Distributors integration
  Scope: `kerf-cloud/distributors/` API surface (mocked HTTP) + `kerf-billing` price lookup.
  File: `packages/kerf-cloud/tests/test_feature_distributors.py`
  Success: 25 part lookups across mocked DigiKey/Mouser/LCSC/Octopart; FX conversion; cache TTL behaviour.

- [ ] T-57 BOM (mech + electronic) consolidation
  Scope: BOM table aggregation across `kerf-parts`, `kerf-electronics`, `kerf-cad-core` weldment / fasteners.
  File: `packages/kerf-cad-core/tests/test_feature_bom_consolidation.py`
  Success: 25 mixed assemblies; deduped quantities; cost roll-up; alternates resolution.

- [ ] T-58 Chat: tool dispatch + tool round-trip
  Scope: `kerf-chat/` plugin → `kerf-cad-core` tool call → file_revision created.
  File: `packages/kerf-chat/tests/test_feature_chat_tool_roundtrip.py`
  Success: 25 chat turns invoking diverse tools; revisions append; assistant message references tool result.

- [ ] T-59 Chat: prompt caching wire-up
  Scope: Anthropic prompt-cache headers reach API; cache-hit metric recorded.
  File: `packages/kerf-chat/tests/test_feature_chat_prompt_cache.py`
  Success: 25 multi-turn sessions; first turn primes cache, subsequent turns hit; provider client mocked.

- [ ] T-60 Workshop: gallery / readme / likes
  Scope: workshop publish flow (`project_workshop_images`, `workshop_likes`, `workshop_readme`).
  File: `packages/kerf-api/tests/test_feature_workshop.py`
  Success: 25 publish/like/edit cycles; primary-image selection; README markdown safe-render.

- [ ] T-61 Library: submissions + moderation
  Scope: `library_part_submissions` lifecycle (draft → submitted → approved/rejected).
  File: `packages/kerf-api/tests/test_feature_library_submissions.py`
  Success: 25 submissions across roles; state-machine guards; admin override path.

- [ ] T-62 File revisions (OSS fine-grained undo)
  Scope: `file_revisions` source∈{user,llm,tool,restore} + compaction (mig 048) + content-ref (049) + sha256 (018).
  File: `packages/kerf-api/tests/test_feature_file_revisions.py`
  Success: 25 edit sequences; restore semantics; compaction preserves sha256 chain; content-ref dedup.

- [ ] T-63 Cloud git refs + GitHub App
  Scope: `kerf-cloud/github_app.py` + `cloud_github_tokens` round-trip (mocked GH HTTP).
  File: `packages/kerf-cloud/tests/test_feature_cloud_git.py`
  Success: 25 git operations (fetch / push / install / uninstall); installation token rotation; PEM keys not leaked.

- [ ] T-64 Billing buckets (kerf_free / kerf_paid / byo)
  Scope: `kerf-billing/buckets.py` + `spend.py` + `scheduler.py` cron close-out.
  File: `packages/kerf-billing/tests/test_feature_billing_buckets.py`
  Success: 25 usage scenarios across all three buckets; spend tally correct; cheap-models-only enforcement on kerf_free; BYO bypasses meter.

- [ ] T-65 Email providers + templates
  Scope: `kerf-cloud/email/` provider switch + template render.
  File: `packages/kerf-cloud/tests/test_feature_email.py`
  Success: 25 transactional sends across providers (mocked SMTP); subject + body render; bounce / suppression list.

- [ ] T-66 STEP tessellation jobs
  Scope: `step_tessellation_jobs` lifecycle + `step_ref_kind` + `step_tess_input_spec`.
  File: `packages/kerf-api/tests/test_feature_step_tess_jobs.py`
  Success: 25 job submissions; queued → running → done state machine; idempotent re-tess; tessellated artifact attaches.

- [ ] T-67 Derived artifacts cache
  Scope: `derived_artifacts` (mig 024) cache hits across exports.
  File: `packages/kerf-api/tests/test_feature_derived_artifacts.py`
  Success: 25 hit/miss/invalidate scenarios; correct lineage on source bump.

- [ ] T-68 Project types (jewelry / mech / electronic / arch / civil)
  Scope: `mig 005` `project_type` + per-type defaults + tool-allow-list.
  File: `packages/kerf-api/tests/test_feature_project_types.py`
  Success: 25 per-type new-project flows; correct seed kinds; default chat system prompt.

- [ ] T-69 Validation / canonical reference modules (audit harness)
  Scope: meta-test asserting every kerf-cad-core / kerf-electronics validation-tagged module has a citable-reference test row.
  File: `packages/kerf-cad-core/tests/test_feature_validation_audit.py`
  Success: enumerate validated modules from `tasks.md` (#162-#184); assert ≥1 reference-anchored test per module; ≥25 modules covered.

---

## Section 2 — Auth pen-test

Real FastAPI app via `kerf-api` test client; SMTP / OAuth providers mocked.
One task per attack class. Each ≥10 cases (boundary, baseline, attacker
variants, timing).

- [ ] T-70 Password lockout + rate-limit
  Scope: login endpoint repeated failure → lockout window; per-IP & per-account.
  File: `packages/kerf-auth/tests/test_pen_password_lockout.py`
  Success: 12 cases — N-1 attempts allowed, Nth locks, unlock after window, lockout does NOT enumerate users by timing.

- [ ] T-71 JWT replay + forgery
  Scope: stolen access-token reuse after logout / rotation; alg=none, alg-confusion, kid-injection.
  File: `packages/kerf-auth/tests/test_pen_jwt_replay_forgery.py`
  Success: 12 cases — none/HS256-via-RS256-pub/kid-traversal all rejected; revoked-token blacklist enforced.

- [ ] T-72 Session expiry + token rotation
  Scope: refresh-token rotation (`refresh_tokens` table), reuse-detection forces re-auth.
  File: `packages/kerf-auth/tests/test_pen_session_rotation.py`
  Success: 12 cases — rotation works, double-use of old refresh revokes family, expired refresh refused.

- [ ] T-73 Password-reset token reuse
  Scope: reset-token single-use, ≤30 min expiry, account-bound.
  File: `packages/kerf-auth/tests/test_pen_password_reset.py`
  Success: 12 cases — single-use enforced, expired refused, cross-account refused, reset invalidates existing sessions.

- [ ] T-74 OAuth state / PKCE
  Scope: Google + GitHub OAuth state randomness + PKCE verifier check.
  File: `packages/kerf-auth/tests/test_pen_oauth_state_pkce.py`
  Success: 12 cases — missing/mismatched state rejected; PKCE downgrade rejected; CSRF on callback caught.

- [ ] T-75 CSRF protection
  Scope: cookie-auth endpoints reject cross-origin POST without CSRF token.
  File: `packages/kerf-auth/tests/test_pen_csrf.py`
  Success: 10 cases — same-origin allowed, cross-origin / null-origin / sub-domain refused, SameSite enforcement.

- [ ] T-76 Account enumeration timing leaks
  Scope: login + reset endpoints constant-time on user-exists vs not.
  File: `packages/kerf-auth/tests/test_pen_enumeration_timing.py`
  Success: 10 cases — response time delta < threshold; identical error text; identical email-sent UX.

- [ ] T-77 API token scope + revocation
  Scope: `api_tokens` table — scope enforcement, revoke is immediate, token prefix lookup not vulnerable to side-channel.
  File: `packages/kerf-auth/tests/test_pen_api_tokens.py`
  Success: 10 cases — out-of-scope call denied; revoked token denied within 1s; bcrypt-compare timing.

- [ ] T-78 Share-link abuse
  Scope: `share_links` max_uses / expires_at / revoked_at; cannot escalate beyond role.
  File: `packages/kerf-auth/tests/test_pen_share_links.py`
  Success: 10 cases — expired/exhausted/revoked refused; viewer cannot mutate; share-link cannot escape project boundary.

- [ ] T-79 Workspace invite hijack
  Scope: `workspace_invites` token random, bound to inviter+invitee email, single-use.
  File: `packages/kerf-auth/tests/test_pen_workspace_invites.py`
  Success: 10 cases — token reuse refused; email mismatch refused; role escalation via tampered invite refused.

---

## Section 3 — RLS / multi-tenant Postgres

Two-user fixture (`user_a`, `user_b`) in separate workspaces. Each task
asserts user A cannot read/write user B's rows via crafted SQL through the
authenticated session role. One task per protected table; ≥10 negative
cases each (SELECT/INSERT/UPDATE/DELETE × {direct row, via join, via foreign-key
escalation}).

- [ ] T-80 RLS: projects
  Scope: cross-tenant SELECT/UPDATE/DELETE on `projects`.
  File: `packages/kerf-core/tests/test_rls_projects.py`
  Success: 12 cases — user A sees only own workspace projects; cannot set `workspace_id` to B's.

- [ ] T-81 RLS: files
  Scope: cross-tenant on `files`, including parent_id traversal.
  File: `packages/kerf-core/tests/test_rls_files.py`
  Success: 12 cases — reparent to other workspace refused; storage_key leak via select refused.

- [ ] T-82 RLS: file_revisions (OSS undo)
  Scope: cross-tenant on `file_revisions` (mig 001 + 002 + 049).
  File: `packages/kerf-core/tests/test_rls_file_revisions.py`
  Success: 12 cases — revision content of B's file not visible; restore-from-B refused.

- [ ] T-83 RLS: chat_threads + chat_messages
  Scope: cross-tenant on `chat_threads`, `chat_messages`.
  File: `packages/kerf-core/tests/test_rls_chat.py`
  Success: 12 cases — thread of B not listable / readable; cannot post into B's thread; tool_call_id forging refused.

- [ ] T-84 RLS: workspaces + workspace_members + workspace_invites
  Scope: cross-tenant on `workspaces` family.
  File: `packages/kerf-core/tests/test_rls_workspaces.py`
  Success: 12 cases — list/join/invite-leak refused; member elevation refused.

- [ ] T-85 RLS: api_tokens + refresh_tokens
  Scope: cross-tenant on auth tokens.
  File: `packages/kerf-core/tests/test_rls_auth_tokens.py`
  Success: 12 cases — token rows of B not visible; cannot insert refresh_token for B.

- [ ] T-86 RLS: usage_events + cloud_user_balances + billing_buckets
  Scope: cross-tenant on billing rows.
  File: `packages/kerf-core/tests/test_rls_billing.py`
  Success: 12 cases — B's spend invisible; cannot insert credit for self; cannot mutate B's balance.

- [ ] T-87 RLS: step_tessellation_jobs + cam_jobs + fem_jobs + sim_jobs
  Scope: cross-tenant on worker job tables.
  File: `packages/kerf-core/tests/test_rls_jobs.py`
  Success: 12 cases — cannot enqueue against B's project; cannot read B's job outputs; status leak via id-guess refused.

- [ ] T-88 RLS: distributor_credentials + user_provider_keys
  Scope: BYO secrets must never leak across tenant.
  File: `packages/kerf-core/tests/test_rls_secrets.py`
  Success: 12 cases — encrypted blob not retrievable; cannot mutate B's record; admin role explicitly required for ops paths.

- [ ] T-89 RLS: upload_sessions
  Scope: cross-tenant on `upload_sessions` (mig 008).
  File: `packages/kerf-core/tests/test_rls_upload_sessions.py`
  Success: 10 cases — session of B not readable; storage_key collision refused; cannot finalize B's session.

- [ ] T-90 RLS: cloud_github_tokens
  Scope: `cloud_github_tokens` + repair (mig 064) cross-tenant.
  File: `packages/kerf-core/tests/test_rls_cloud_github_tokens.py`
  Success: 10 cases — installation token of B's not visible; cannot bind B's installation to A's project.

- [ ] T-91 RLS: project_workshop_images + workshop_likes + workshop_readme
  Scope: workshop assets — public read OK, write tenant-scoped.
  File: `packages/kerf-core/tests/test_rls_workshop.py`
  Success: 10 cases — public can read published; only owner can mutate / set primary / publish README.

- [ ] T-92 RLS: derived_artifacts
  Scope: derived-artifact rows (mig 024) cross-tenant.
  File: `packages/kerf-core/tests/test_rls_derived_artifacts.py`
  Success: 10 cases — artifact of B not readable; lineage column cannot be forged.

- [ ] T-93 RLS: model_prices admin-only
  Scope: `model_prices` (mig 050) writable only by admin role.
  File: `packages/kerf-core/tests/test_rls_model_prices.py`
  Success: 10 cases — non-admin INSERT/UPDATE refused; SELECT public; admin elevation enforced via account_role.

- [ ] T-94 RLS: library_part_submissions
  Scope: `library_part_submissions` (mig 020) submitter-scoped + admin moderation.
  File: `packages/kerf-core/tests/test_rls_library_submissions.py`
  Success: 10 cases — submitter sees own, admin sees all, non-admin cannot approve.

---

## Section 4 — Frontend E2E (Playwright)

Persona-scoped flows the chat agent must never break. Build on existing
`tests/e2e/specs/` patterns and `tests/e2e/pages/` page objects. Each
spec runs against a seeded dev server with mocked Anthropic and a clean
Postgres schema. ≥10 user-visible assertions per spec.

- [ ] T-95 E2E jewelry persona
  Scope: signup → new jewelry project → chat "design a 6-prong solitaire 1ct round D-VVS1 platinum size 6" → render → STL export.
  File: `tests/e2e/specs/persona_jewelry.spec.ts`
  Success: SKU built; PBR materials applied; cost panel populated; STL downloads & is manifold.

- [ ] T-96 E2E mechanical persona
  Scope: signup → new mech project → import FreeCAD fixture → chat "add 4 M4 holes on top face" → unfold sheet metal → drawing → PDF.
  File: `tests/e2e/specs/persona_mech.spec.ts`
  Success: feature tree shows hole pattern; unfold succeeds; drawing dimensions auto; PDF export downloads.

- [ ] T-97 E2E ECAD persona
  Scope: signup → new electronic project → import KiCad fixture → chat "run DRC + generate Gerbers + BOM" → fab zip.
  File: `tests/e2e/specs/persona_ecad.spec.ts`
  Success: DRC report shown; Gerber zip downloads; BOM table renders; cost roll-up against mocked distributors.

- [ ] T-98 E2E architect persona
  Scope: signup → new arch project → space program from chat → IFC export → import back.
  File: `tests/e2e/specs/persona_architect.spec.ts`
  Success: spaces visible in 3D; IFC export valid; round-trip preserves spaces & GlobalIds.

- [ ] T-99 E2E civil persona
  Scope: signup → new civil project → alignment + earthwork from chat → cut/fill report → DXF export.
  File: `tests/e2e/specs/persona_civil.spec.ts`
  Success: alignment renders; earthwork volumes match expected within 2%; DXF downloads.

- [ ] T-100 E2E automotive persona (composites + clash)
  Scope: signup → new mech/auto project → assembly load → composites layup + clash check → report.
  File: `tests/e2e/specs/persona_automotive.spec.ts`
  Success: clash report lists expected interferences; composites layup table renders; export OK.

- [ ] T-101 E2E billing flow (paid bucket)
  Scope: free user → upgrade simulated → consume usage → invoice line items appear → BETA-mode toggle hides billing UI but features remain.
  File: `tests/e2e/specs/persona_billing.spec.ts`
  Success: usage tally matches API; BETA flag hides Pricing route; features still available.

- [ ] T-102 E2E share-link viewer
  Scope: owner creates viewer share-link → second browser opens → cannot mutate → expiry observed.
  File: `tests/e2e/specs/persona_share_link.spec.ts`
  Success: viewer sees project; mutate UI disabled; expired token redirects to login.

- [ ] T-103 E2E workshop publish
  Scope: complete project → publish to workshop → gallery shows → like → README renders.
  File: `tests/e2e/specs/persona_workshop.spec.ts`
  Success: gallery card has primary image; README markdown safe-rendered; like count increments.

- [ ] T-104 E2E chat regression matrix
  Scope: chat agent does NOT silently break the editor — 10 representative tool calls (sketch / feature / sheet-metal / weldment / drawing / PCB / jewelry / arch / FEM / CAM) each leave the project re-openable.
  File: `tests/e2e/specs/persona_chat_regression.spec.ts`
  Success: after each tool call: project list refresh, reopen, last revision restorable, no orphan jobs.

---

STATUS: COMPLETE
