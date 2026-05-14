# Kerf — Roadmap

This is the public roadmap for Kerf, an open-source chat-driven CAD tool. It
captures shipped capabilities, in-flight work, and the bigger phases ahead.
The data-model + API spec lives in [docs/architecture.md](./docs/architecture.md); this
document is about *direction*, not interface details.

Kerf is dual-licensed: the OSS core (MIT, see [LICENSE](./LICENSE)) and the
hosted-tier code under `packages/kerf-{billing,cloud}/` and `src/cloud/`,
governed by [LICENSE-CLOUD](./LICENSE-CLOUD).

---

## Vision

A chat-driven CAD tool that produces real engineering output. Code-first
(JSCAD) for parametric work, visual sketcher with constraints for 2D, real
B-rep features (OpenCascade) for solid modeling parity with FreeCAD/SolidWorks,
TechDraw-style 2D drawings for documentation. Browser-native, single-binary
local install, optional hosted tier with billing + workshop sharing + git.

---

## Status overview

| Area | Status | Notes |
|---|---|---|
| **Auth + projects + files + chat (CRUD)** | ✅ shipped | Postgres-backed, JWT, Google OAuth |
| **JSCAD authoring loop** | ✅ shipped | Worker-based eval, IndexedDB mesh cache, file-revisions undo, 4-tier debounce |
| **2D parametric sketcher (planegcs)** | ✅ shipped | Constraints (parallel, equal, perpendicular, distance, angle, tangent), drag-to-solve, color-coded DOF state |
| **Assembly model (Object/Part/Component)** | ✅ shipped | Insert dialog with checkboxes, Copy/Delete-Object via revisions |
| **2D technical drawings (TechDraw-flavored)** | ✅ shipped | Multi-sheet, dimensions (distance/radius/diameter/angular/baseline/chain/ordinate), section hatching, leaders/balloons, GD&T frames, centerlines, break-lines |
| **Cloud: Workshop sharing** | ✅ shipped | Free-sharing gallery, like + fork, OnShape-style insert dialog |
| **Cloud: Paystack billing** | ✅ shipped | USD pricing, ZAR settlement, FX refresh, webhook-credited prepaid balance |
| **Cloud: Git (commits + branches + merge + GitHub sync)** | ✅ shipped | go-git, multi-lane lattice graph view, GitHub OAuth, AES-GCM-encrypted tokens |
| **Filesystem storage backend** | ✅ shipped | Projects mirror to disk as folders for local-install workflows |
| **Single-binary build with embedded frontend** | ✅ shipped | `npm run build` → ~32 MB self-contained `kerf` |
| **Plugin architecture + monorepo packages/** | ✅ shipped | `kerf-core` provides FastAPI app factory + `kerf.plugins` entry-point loader (`packages/kerf-core/src/kerf_core/app.py`, `plugin.py`, `utils/topo_sort.py`). 19 plugin packages under `packages/`: kerf-core, kerf-sdk, kerf-auth, kerf-api, kerf-chat, kerf-v1, kerf-billing, kerf-cloud, kerf-cad-core, kerf-tess, kerf-fem, kerf-cam, kerf-topo, kerf-mates, kerf-bim, kerf-electronics, kerf-imports, kerf-render, kerf-workers. Each declares `async register(app, ctx) -> PluginManifest`. Root `pyproject.toml` declares persona extras (`api-only` / `mech` / `electronics` / `bim` / `full` / `compute-only`) and a uv workspace. Cloud-gated plugins (kerf-billing, kerf-cloud) early-return dormant manifests when `ctx.cloud_enabled=False`. Test suite: 864 passing / 21 skipped across all packages. |
| **Brew formula + curl install** | ✅ shipped | Homebrew tap + `install.sh` |
| **Test runner (OSS + cloud, separate)** | ✅ shipped | 4 OSS scenarios, 4 cloud scenarios, surfaces real bugs |
| **Drawing snap + projection visibility** | ✅ shipped | Endpoint / midpoint / center / intersection snap end-to-end. Helpers `extractSnapTargets` / `resolveSnap` / `snapLabel` in `src/lib/drawingSnap.js` (20-assertion vitest); integration in `DrawingView.jsx` covers all snap-aware tools (linear / aligned / radius / diameter / baseline / chain / ordinate / angular / measure / leader / centerline / break / surface_finish / weld / gdt / balloon) with zoom-aware tolerance, Alt-key bypass, localStorage `snapEnabled` toggle, kind-specific glyphs. |
| **Feature panel: Pad / Pocket / Revolve** | ✅ shipped | OCCT Phase 2/3 complete: `feature_pad` / `feature_pocket` / `feature_revolve` LLM tools + `feature_*` toolbar in `FeatureView.jsx`; full B-rep ops (Hole, Fillet, Chamfer, Shell, Sweep1/2, NetworkSrf, BlendSrf, RotateFace, Push-Pull, LinearPattern, PolarPattern, MirrorPattern); face/edge gumball direct-modeling; integration scenarios in `feature_files.go`. |
| **Cloud git → object-storage Storer** | ✅ shipped | `packages/kerf-core/src/kerf_core/storage/git_storer.py::S3GitStorer` — pygit2-based bulk-sync storer for bare repos on R2/S3. Stateless serverless deploys, no local persistent disk required. Pack/loose objects uploaded **before** refs for crash-consistency; sentinel `_marker` object provides ETag-based optimistic concurrency (concurrent pushers get `StorerConcurrencyError`); orphans batch-deleted via `delete_objects`. OSS/local-install keeps the on-disk pygit2 path — the Storer is only constructed when `STORAGE_BACKEND=s3`. 6 hermetic moto integration tests in `packages/kerf-core/tests/test_git_storer.py` (round-trip, empty bootstrap, multi-commit + repack + orphan cleanup, race detection, batch delete, force-replace). |
| **Large-file handling for git sync (STEP / binary imports)** | ✅ shipped | **Phase 1 shipped**: migration `033_step_ref_kind.sql` adds the `.step-ref` pointer kind; files ≥ 5 MB are committed as a small JSON pointer (`{hash, size, original_name}`) content-addressed into object storage. Kerf's import path resolves the pointer transparently via CDN. Git history stays lean. **Phase 2 (only if clone-outside-Kerf demand emerges):** Git LFS via direct Batch API — implement the 3-line pointer format + ~2 HTTP endpoints in the go-git sync path. |
| **Test scenarios: assembly + sketcher + drawing** | ✅ shipped | `backend/cmd/test/scenarios/{sketcher,drawings,cross_project_parts}.go` cover OSS integration; cloud-side `scenario_workshop_{parts,listings,verified_filter}.go` + `scenario_library_part_detail.go` round out the picture. |
| **Sketcher v2 improvements** | ✅ shipped | Trim, extend, ellipse, B-spline (cubic), fillet (2-line corner UI), mirror, linear pattern, polar pattern; 6 new constraints (horizontal distance, vertical distance, symmetric, block, equal angle, parallel lines); arc/circle edge projection for external geometry; multi-loop holes in extrude pockets; 3D backdrop overlay. Pure helpers in `src/lib/sketchOps.js` / `sketchGeom2.js`, canvas tools wired in `SketchView.jsx`, LLM tools `sketch_trim` / `sketch_extend`, vitest + integration coverage. |
| **Sketcher v1 fixes** | ✅ shipped | Live-tooling regression (line tool wiping `pendingPoints` on every solver round-trip, breaking the sketch→Pad/Pocket/Hole handoff) fixed in `6dc18ee` via the `lastSketchRef` pattern in `SketchView.jsx`: every locally-produced sketch reference is stashed before `onChange`/`onSolved` calls, and the resync `useEffect` only clears pending state when the incoming prop is a true external replacement (LLM restore / undo), not a self-write bounce-back. 757/757 vitest pass; `sketcher.test.js` covers solver integration + multi-click data flow + JSON round-trips; `sketchGeom2.test.js` covers the Pad handoff path. Follow-on `ac8d9e9` adds further tooling. Remaining nit: an OCCT end-to-end "line draw → solve → Pad → expected vertex count" integration test is still missing — moved to the [Sketcher v2 row]/test-coverage backlog. |
| **Equations / global parameters** | ✅ shipped | `.equations` JSON kind; mathjs evaluator (`src/lib/equations.js`); EquationsEditor (full-bleed table); injected into JSCAD as `params` arg, `.feature` + `.sketch` via `${name}` placeholders; backend `read_equations` / `set_equation` LLM tools + `docs/llm/equations.md`. Multi-file merge with last-loaded-wins. |
| **Configurations / variants** | ✅ shipped | Per-file parameter overrides round-trip in `.part` / `.feature` / `.sketch` JSON (`{default_config, configurations:[{id, label, params}]}`); editor config dropdown + ConfigurationsPanel slide-out; assembly components pin via `config_id` (frontend `parseAssembly` + backend BOM both honor); BOM groups by `(file_id, config_id)` and surfaces a `config_label` chip in BOMTable; LLM tools `add_configuration` / `set_active_config` + `docs/llm/configurations.md`; integration scenario `configurations` covers Part round-trip, assembly references, BOM rollup, and tool repin/clear. |
| **Materials database (`.material` Library kind)** | ✅ shipped | `.material` JSON file kind with mechanical/thermal/physical groups; MaterialEditor with grouped SI-unit fields; LLM tools `read_material` / `find_material_by_name` / `set_part_material` + `docs/llm/material.md`; `seed/materials/` + `npm run seed:materials` populates a curated `Materials Library` project owned by the system user. 55 curated engineering materials seeded (expanded from 20). Consumed downstream by FEM, tolerance, Part defaults, drawing callouts. |
| **3D assembly mates (Tier 0 foundation)** | ✅ shipped | Coincident / concentric / parallel / perpendicular / distance / angle / tangent. Pure-Python `GeometricConstraintSolver` (gradient-descent, 100-iter) in `packages/kerf-mates/src/kerf_mates/solver.py`. LLM tools: `add_mate`, `delete_mate`, `list_mates`, `solve_assembly`. pyworker route `/run-mates`. REST endpoint `POST /api/projects/{pid}/files/{fid}/solve-mates`. `.assembly` JSON `mates: [{type, a:{component_id, feature, feature_id}, b:{…}, value?}]`. Frontend: `MatesPanel.jsx` collapsible card inside AssemblyEditor (type selector, A/B ref rows with manual text + BREP face/edge viewport picker, Add/Delete, live solve result chip). Pick flow: "Pick from viewport" → Editor enters face-pick mode → amber banner "Click a face or edge on ref A/B…" with Esc cancel → `mateRefFromPick()` converts Renderer hit → ref auto-populated. `mateRefFromPick` exported from `src/lib/assembly.js`; strips `/origPartId` suffix for multi-object components. Vitest cases in `assembly.test.js` + `matesPanel.test.js`. |
| **Scripting: `.script.py` via `kerf-sdk`** | ✅ shipped | `/v1/rpc` JSON-RPC dispatcher in `packages/kerf-v1/src/kerf_v1/routes.py` over the existing LLM tool registry (method→tool map for files / equations / configurations / revisions / docs); `script` file kind + `extension` column (migrations `026_kind_script.sql` + `029_script_extension.sql`); `api_tokens` table (migration `025_api_tokens.sql`) with `scopes jsonb` + `last_used_at` + soft-revoke; create/list/revoke endpoints in `packages/kerf-auth/src/kerf_auth/routes.py` mounted at `/api/api-tokens`; `WorkspaceSettings.jsx` API Tokens card (issue/list/revoke, "shown once on creation" warning + copy); `ScriptEditor.jsx` recognizes `.script.py` and shows `pip install kerf-sdk` install hint; `packages/kerf-chat/llm_docs/script.md` documents the surface. **kerf-sdk/ in-monorepo**: `packages/kerf-sdk/`. `kerf-sdk/pyproject.toml` (hatchling, `httpx>=0.27`); `src/kerf/{__init__,auth,client,tools}.py` — `connect()` / `from_env()` / `Kerf`, JSON-RPC 2.0 envelope, namespaced wrappers `kerf.files.*` / `kerf.equations.*` / `kerf.configurations.*` / `kerf.revisions.*` / `kerf.docs.*`; `tests/test_client.py` 7 respx-mocked tests (envelope, auth header, error mapping, namespaces, `from_env`, ctx manager); `.github/workflows/publish.yml` PyPI trusted-publish on `sdk-v*` tags. Local install: `pip install -e kerf-sdk/`. Decision: monorepo eliminates contract drift, allows atomic tool additions, lower solo-founder overhead. Hosted execution and second-language bindings (TS/Lua/Go/Rust against the same OpenAPI spec) are demand-gated S5/S6 — architecture supports them as alternative endpoints, not redesigns. |
| **`.feature` file kind + OCCT integration (Phase 2)** | ✅ shipped | Real B-rep features: Pad / Pocket / Revolve / Hole / Fillet / Chamfer / Shell / Sweep1 / Sweep2 / Loft / Push-Pull / RotateFace / LinearPattern / PolarPattern / MirrorPattern. `feature_*` LLM tools per op + integration scenario (60 assertions). Coexists with the JSCAD path; FeatureView toolbar gates Op palette, OCCT worker handles geometry, planegcs solves embedded sketches. |
| **Edge/face selection + direct modeling (Phase 3)** | ✅ shipped | Face + edge selection state in `FeatureRenderer.jsx` (`featureSelection: { faceIds, edgeIds }`), face gumball with translate/rotate handles emits `push_pull` / `rotate_face` nodes, edge gumball drag-to-fillet emits `feature_fillet` with the dragged radius. Bidirectional highlight panel↔schematic via `selectedCircuitComponentId`. Per-frame re-orient on camera orbit. |
| **FEM: mechanical analysis** | ✅ shipped | **FEniCSx primary** (LGPL3, Python-native, active UK/US consortium dev, UFL differentiable, multiphysics-natural, GPU on roadmap); CalculiX second-solver behind same `pyworker` `/run-fem` route for FreeCAD-bit-exact compat + frictional contact when demanded. Gmsh for meshing in both. `.fem` file kind wired: `POST/GET /api/.../fem` + `/fem/status`, `fem_run` / `fem_job_status` LLM tools, `FEMView.jsx` wired in `Editor.jsx`, gmsh/dolfinx/ccx gated with `ENGINE_PENDING_WARNING` sentinels. **dolfinx UFL forms wired**: real small-strain linear elasticity (σ = λ tr(ε) I + 2μ ε, Dirichlet + Neumann BCs, von Mises post-processing, FoS). Bonded contact via shared-node conformal Gmsh mesh (`occ.fragment()`). Returns `node_displacements` per-node vector + `stresses` per-cell DG0 array. **Deformed-shape 3D overlay** in `FEMView.jsx`: Three.js morphed by `displacement * scale_factor`; UI scale slider 1–200×; colour by displacement magnitude or von-Mises stress; colour bar legend; toggle show/hide. **BufferGeometry passthrough**: `Editor.jsx` extracts display mesh from current `w.parts` via `extractDisplayGeometryFromParts` and passes it to `FEMView` → `FEMDeformedShape` so a lit + wireframe morphed surface is rendered instead of the point-cloud proxy when a source part is loaded. **Modal analysis SLEPc wired**: GHEP K x = λ M x via `SLEPc.EPS` (Krylov-Schur + SINVERT shift-invert); frequencies Hz = sqrt(λ)/(2π); mode shapes returned; `_SLEPC_AVAILABLE` gate. **CalculiX modal wired**: `*FREQUENCY,NMODES=N` step; `.dat` eigenvalue parser (ω² → Hz); `.frd` mode-shape parser; same result schema (`frequencies` + `mode_shapes`) as FEniCSx path; `_CALCULIX_AVAILABLE` gate returns `ENGINE_PENDING_WARNING` when `ccx` absent. **Multi-body multi-material BCs**: `material_props` accepts `[{body_tag, material_props}]` list; Lamé + density assembled as piecewise-constant DG0 fields per cell-tag region; backwards-compat with single-dict form. Pytests: cantilever beam (Euler-Bernoulli, 5% tol) + FEniCSx modal (first bending freq analytical, 5% tol, `importorskip` SLEPc) + CalculiX modal (`test_fem_calculix_modal.py`, `shutil.which` skip). Vitest: `extractDisplayGeometryFromParts` (JSCAD Geom3 + BufferGeometry cases) + displacement-scaling math. |
| **Tolerance stack-up** | ✅ shipped | `.tolerance` JSON file kind; `tolerance_stack` + `tolerance_monte_carlo` LLM tools; `worst_case` / `rss` / `monte_carlo` pure helpers in `packages/kerf-mates/src/kerf_mates/tolerance.py`; `POST /api/projects/{pid}/files/{fid}/tolerance/run` API route (worst_case / rss / monte_carlo methods); frontend `src/lib/tolerance.js` (pure functions for in-browser compute); `ToleranceView.jsx` — dimension-chain table, WC+RSS summary cards, inline SVG histogram for Monte-Carlo output, Run button; wired in `Editor.jsx` for `.tolerance` file kind. **Automatic chain-walk shipped**: `tolerance_auto_chain` LLM tool (registered via `packages/kerf-mates/src/kerf_mates/plugin.py`) walks the assembly mate graph by BFS between two feature references and auto-builds the dimension chain. Pure helper `build_chain_from_assembly` in `packages/kerf-mates/src/kerf_mates/chain_walk.py`. Per-mate `tolerance: {plus, minus}` slot added to `.assembly` schema (backward-compatible). `packages/kerf-chat/llm_docs/tolerance.md` documents full schema + all methods + chain-walk. 12 pytest-style tests in `packages/kerf-mates/tests/test_tolerance_chain_walk.py`. |
| **CAM toolpath generation** | ✅ shipped | OpenCAMlib (LGPL 2.1) + pythonOCC, all try/except gated with mock fallback. 2.5D ops (face/contour/pocket/drill/profile) + 3D parallel/waterline + lathe (X-Z plane, G18/G96, multi-pass roughing from profile) + 5-axis stub. B-rep wire extraction via `TopExp_Explorer` → planar Z-normal face selection → `BRepTools.OuterWire` + inner-wire walk → `GCPnts_QuasiUniformDeflection` discretisation replaces bbox fallback for contour/pocket. STEP→STL via `STEPControl_Reader` + `BRepMesh_IncrementalMesh` (0.1 mm linear deflection). G-code post-processors: LinuxCNC / GRBL / Mach3 / Fanuc. `.cam` file kind wired: `POST/GET /api/.../cam` + `/cam/status`, `cam_run` / `cam_job_status` LLM tools, `CAMView.jsx`, `llm_docs/cam.md`. Tests: `test_cam_step.py` (STEP→STL) + `test_cam_advanced.py` (16 cases covering wire extraction, parallel_3d, waterline, lathe, 5-axis stub). Caveats: lathe emits plain G1 moves (no G71/G72 canned cycles); `ocl.AdaptiveWaterline` requires OCL built with Boost.Polygon, falls back to perimeter-at-Z when absent. |
| **Topology optimization** | ✅ shipped | Density-field SIMP via FEniCSx; `dolfinx`/`gmsh`/pythonOCC imports gated with try/except so pyworker boots without them. `.topo` file kind wired; `topo_run` LLM tool; pyworker `POST /run-topo` — when dolfinx+gmsh are available meshes the real `.feature` STEP via `gmsh.model.occ.importShapes` + `dolfinx.io.gmshio.read_from_msh`, runs full SIMP loop (Heaviside filter, OC update, Heaviside projection) with loads/BCs from `.topo` spec (face_tag-indexed Dirichlet + Neumann); when Gmsh absent falls back to unit-cube mesh; marching-cubes (skimage) + Laplacian smoothing (`smoothing_iterations`, default 3) + NURBS surface fitting per connected component (`GeomAPI_PointsToBSplineSurface`, PCA-plane projection, scipy cKDTree grid sampling) with per-component faceted fallback + pythonOCC BRep sewing exports STEP stored as new `kind='step'` file with `output_mesh_file_id` populated; multi-body optimization via `occ.fragment()` conformal mesh + per-body `volume_fraction`/`filter_radius_mm` arrays + independent OC updates sharing interface displacement DOFs; when not available returns `ENGINE_PENDING_WARNING` sentinel. `TopoView.jsx` renders spec params, results, `DensityFieldHeatmap` (SVG X-Y projection of density field), `DensityMeshViewer` (GLB when output_mesh_file_id is set); wired in `Editor.jsx` for `.topo` kind. `llm_docs/topo.md` documents full schema + BC/load spec + face_tag convention + multi-body fields. `packages/kerf-topo/tests/test_topo_phase2.py` + `test_topo_polish.py` cover Gmsh meshing, SIMP non-triviality, NURBS round-trip, smoothing RMS reduction, multi-body per-body density divergence (all skipped without deps). |
| **Architecture: IFC + text-DSL** | ✅ shipped | `.bim` text-DSL (or JSON) → IfcOpenShell IFC4 compiler → `.ifc` artifact → web-ifc/Three.js viewer (`BIMView.jsx`). Supports walls/slabs/spaces/openings/levels/site. pyworker `POST /compile-ifc` + `POST /compile-bim`. Backend tools: `create_bim`, `read_bim`, `compile_bim_to_ifc`, `read_ifc`. IfcOpenShell import gated with try/except — server boots without it. LLM doc page at `packages/kerf-bim/llm_docs/bim.md`. |
| **NURBS surfacing (Phase 4)** | ✅ shipped | sweep1/sweep2/networkSrf/blendSrf surface creation tools + display. Python NurbsSurface layer (`backend/geom/`). LLM tools `feature_sweep1/2/network_srf/blend_srf` + `surface_continuity` query/enforce tool (C0/C1/C2 for sweeps/network; G0/G1/G2 for blend). `.surf` file kind documented. NURBS tessellated for display by OCCT worker. **Scope intentionally bounded**: surface creation + display only. NURBS trimming/booleans (deep OCCT kernel work) is multi-year and deliberately out of scope — for that depth of CAD, full Rhino-tier requires a multi-year kernel project tracked separately. |
| **Phase 4a: jewelry-priority surfacing** | ✅ shipped | All three ops live in `src/lib/occtWorker.js`: `opSweep2` wraps `BRepOffsetAPI_MakePipeShell` with rail2 as auxiliary spine (Frenet fallback); `opNetworkSrf` tries `GeomFill_BSplineCurves` first, falls back to `BRepOffsetAPI_ThruSections` over U-curves with V-curves advisory; `opBlendSrf` uses `BRepFill_Filling` with two edge constraints, returns the blend face only. Continuity args: `C0/C1/C2` for networkSrf (default C1), `G0/G1/G2` for blendSrf (default G1). LLM tools `feature_sweep2` / `feature_network_srf` / `feature_blend_srf` registered in `surfacing_tools.go`. FeatureView toolbar entries under "Surfacing". `feature_files.go` scenario covers all three end-to-end (89 assertions total). |
| **Phase 4b: direct face manipulation (gumball)** | ✅ shipped | Face gumball: 3 translate arrows + 3 rotate rings, anchored at face centroid; drag commits `push_pull` (translate) or `rotate_face` (rotation) feature nodes. Edge gumball: 1D radial handle perpendicular to selected edge; drag commits `feature_fillet` with dragged radius. Per-frame re-orient on camera orbit (rAF self-host). 7 vitest covering centroid/projection math; 8 backend assertions for `rotate_face` round-trip. |
| **Auth-optional removal** | ✅ shipped | Local-mode-only: `[server].local_mode = true` (the OSS default) gates a new `POST /auth/bootstrap-local` endpoint that auto-creates a singleton user + workspace and returns a session, idempotent on subsequent calls. Frontend's `useCloudConfig` surfaces the flag; `App.jsx` calls `tryBootstrapLocal()` after the existing `/api/bootstrap` probe and redirects `/`, `/login`, `/signup` to `/projects` once authed. Cloud builds force `local_mode=false` and `/auth/bootstrap-local` returns 404 — multi-user signup/login is unchanged. Override at runtime via `KERF_LOCAL_MODE`. |
| **Performance: server-side STEP pre-tessellation** | ✅ shipped | **Cloud-tier only**. `packages/kerf-tess/src/kerf_tess/worker.py::AutoTessWorker` wakes on PG `LISTEN/NOTIFY` `step_file_uploaded`, claims `step_tessellation_jobs` rows with `FOR UPDATE OF j SKIP LOCKED`, fetches the STEP blob, calls pyworker `POST /run-tess` (pythonOCC — wazero infeasible per Emscripten/WASI mismatch), stores the GLB at `meshes/step/<sha256>.glb` plus a `derived_artifacts(source_file_id, content_sha256, 'step_mesh')` row for content-hash idempotency, updates `files.mesh_storage_key`. Cloud-gated in `packages/kerf-workers/src/kerf_workers/runner.py`: `auto_tess_count = 1` only when `cloud_enabled and not local_mode`. NOTIFY fired from upload-finalise paths. Failure paths: timeout → error row, pyworker failure → error row (worker survives), stuck-running rows >10min re-queued on next loop, soft-fail on pyworker unavailable. Structured per-job log `auto_tess job_id=… file_id=… status=done|error sha256=… mesh_size=… duration_ms=…`. Migration `047_step_tess_input_spec.sql` adds `input_spec jsonb` + `content_sha256` columns + extends `derived_artifacts.derived_kind` check with `step_mesh`. Hermetic tests in `packages/kerf-tess/tests/test_auto_tess_worker.py` (12 cases: happy-path, idempotent cache hit, missing/empty storage, pyworker failure/timeout, deleted-file skip, input_spec passthrough, empty GLB). OSS local-install path stays browser-only — preserves single-binary brew/curl install. Big-STEP OSS users can pre-tessellate locally via `kerf-sdk`. |
| **Performance: diff-based + compressed revisions** | ✅ shipped | Migration `1746577000000_revision_diffs.sql` adds `parent_id` + `delta_kind` (`base`|`diff`) + content-hashing. Each Nth revision is full-content; in between are unified-diff payloads. Revisions handler reconstructs by walking the chain to the nearest base. 82× shrink measured on typical edit patterns. `cmd/migrate-revisions/` CLI ports historical revisions to the new shape. |
| **Project-type enum (mechanical / electronics / architecture …)** | ❌ replaced | Superseded by free-form `projects.tags TEXT[]` (see "Drop project types → free-form tags" row below). Single-enum design rejected — projects often span domains (a robot has mech + electronics + circuit), so tags compose freely. |
| **Drop project types → free-form tags** | ✅ shipped | `projects.project_type` enum replaced by `projects.tags TEXT[]` with a GIN index. Migration backfills the old single value into a 1-element tags array. Create dialog renders preset tag chips (Mechanical / Electronics / Architecture / Jewelry / PCB / Robotics / Drone / Lighting) + a free-text input + an explicit Starter dropdown (`jscad` / `circuit` / `blank`). Workshop filter is a multi-select tag chip strip backed by repeatable `?tag=` URL params (ANDed). LLM prompt addendum reads the tags array. BRep stays a file kind (`.feature`), not a project type — compose freely with `.jscad`, `.circuit.tsx`, `.assembly` in the same project. |
| **Electronics projects via tscircuit** | ✅ shipped | `.circuit.tsx` file kind, `circuitRunner.js` compiles via tscircuit core, `SchematicView` / `PCBView` / 3D-board viewer render via `circuit-to-svg` + JSCAD; LLM edits via `edit_file` against the TSX (doc page `circuit.md`). Drag-to-move components on schematic + PCB (snap 0.1 / 0.5mm; Alt disables snap), `appendComponent` / `nextRefdes` / `appendTrace` / `appendProbe` source-edit helpers, LibraryPicker for adding parts, V/I probe tool, bidirectional component highlight. |
| **Cross-project parts (PCB-as-part in mechanical assembly)** | ✅ shipped | Phase 3 complete: `bulk_refresh` endpoint, `lock_assembly` + lockfile pattern, diff tooltip on out-of-date external components. Earlier phases — schema + resolver + LLM tool + UI tab + stale indicator + Update CTA: `external_ref` `{project_id, file_id, kind, pin}` slot on Components; `tracking_latest` (HEAD) or revision-pinned; `loadExternalParts(ref)` dispatch in `assembly.js`; `assembly_add_external_component` LLM tool; AssemblyEditor's "From project" picker (3-step modal) + emerald `↗ project-name` badge + amber "out of date" chip when source advances past `last_seen_updated_at` (click → `restampExternalRefSeen` acknowledges). Three artifact kinds wired (`board_3d` / `board_outline_2d` / `mesh`). Phase 2 cache shipped: `derived_artifacts` table + bidirectional `POST /api/projects/{pid}/files/{fid}/derived` lookup + `POST /derived/store` populate + `DELETE /derived` purge (16 MiB payload cap, ON CONFLICT idempotent). `board_outline_2d` shipped: `extractBoardOutline(circuitJson)` produces a real `.sketch` Geom2 polygon (3-tier fallback: explicit `pcb_board.outline` → `width×height` rectangle → 10×10mm placeholder). LLM doc page at `packages/kerf-chat/llm_docs/cross_project.md` + `derived_cache.md`. |
| **Electronics: SPICE simulation** | ✅ shipped | Server-side via `pyworker` `/run-spice` (ngspice subprocess) + `sim_jobs` table + `SPICEWorker` queue consumer + `POST /api/projects/{pid}/files/{fid}/sim` enqueue. Emitter (`src/lib/circuitToSpice.js` walks CircuitJSON → `.cir` netlist), schematic Probe tool (`appendProbe`/`removeProbe`/`renameProbe`/`parseProbes` + V/I toggle + visual indicator + rename UX), `injectProbeRecords` synthesises `simulation_probe` records at compile time, `.simulation` file kind with backend constraint + scenario, SimulationView with `parseSimulation` + uPlot waveform charting (lazy chunk ~22KB gzip) + table-view toggle, `add_probe`/`remove_probe`/`rename_probe` + `run_simulation` LLM tools, doc pages at `packages/kerf-chat/llm_docs/probe.md` + `simulation.md`. Client-side WASM path deferred — no maintained `ngspice-wasm` package exists upstream; pyworker is OSS-installable. |
| **Electronics: RF simulation** | ✅ shipped | S-parameter analysis via scikit-rf. `packages/kerf-electronics/src/kerf_electronics/tools/rf.py` computes VSWR, return loss dB, insertion loss dB, Rollett K, max available gain; Smith chart SVG via matplotlib. Backend LLM tools: `run_rf_study`, `rf_job_status`, `import_touchstone`. `.rf-study` file kind. `RFView.jsx` renders Smith chart + tabular metrics (min/center/max) + VSWR freq-domain plot. `packages/kerf-electronics/llm_docs/rf.md` covers full workflow. openEMS field solver: stub only (Phase 2). |
| **Electronics: autorouting** | ✅ shipped | FreeRouting JAR integration. `packages/kerf-electronics/src/kerf_electronics/freerouting/freerouting.py`: jar auto-download+cache (`~/.cache/kerf/freerouting/FreeRouting.jar` from freerouting/freerouting v1.9.0), progress callback via `Popen` stream, configurable passes (`num_passes`), via budget (`max_vias`), layer-count arg. `packages/kerf-electronics/src/kerf_electronics/tools/autoroute.py`: CircuitJSON → Specctra DSN (`dsn_writer.py`) → FreeRouter subprocess → SES parse (`ses_reader.py`) → CircuitJSON with routes. Backend tool `autoroute_circuit` wired. `PCBView.jsx` gains Autoroute button (calls `onAutoroute`, shows running/done/error states). ML-based reroute (DeepPCB-style) is Phase 2. |
| **Import: KiCad** | ✅ shipped | **Tier 1**: `/import-kicad` pyworker route parses `.kicad_sch` / `.kicad_pcb` → `.circuit.tsx`. LLM tool `import_kicad` wired. **Tier 2**: `/import-kicad-library` pyworker route parses `.kicad_sym` symbol libs → Library Parts with `schematic_symbol` pin metadata; `.kicad_mod` / `.pretty/` footprint libs → Library Parts with `pcb_footprint` pad metadata; 3D STEP model paths surfaced in `model_3d_paths` for `import_step` follow-up; `import_kicad_library` LLM tool writes `kind='part'` files deduped by sha256 content hash. **Tier 3** (lossless round-trip + full layout fidelity) explicitly out of scope. See "Imports from external CAD/EDA tools" section at the bottom for the full plan. |
| **Import: FreeCAD** | 📋 planned | Mechanical-CAD ingest. Closest kernel match to Kerf (both OpenCascade), most complex source data model. Tier 1: Part + PartDesign features → `.feature` + `.sketch` (BRep lifted directly, no re-evaluation). Tier 2: Sketcher constraints + Spreadsheet → `.equations` + TechDraw drawings + Materials Library. Tier 3 (organic): Python-macro migration positions kerf-sdk as natural next step. Other workbenches (FEM/Path/BIM) out of scope — users move to Kerf equivalents. See bottom section for full plan. |
| **Import: OpenSCAD** | ✅ shipped | Browser-side parser (no `pyworker` dep) emits `.jscad` source preserving the parametric model. 18 vitest tests passing. Escape hatch: run OpenSCAD binary as a subprocess for exotic features (`surface()`, customizer hints), import resulting STL as mesh (lossy). |
| **Library system v1 (Parts + BOM)** | ✅ shipped | `kind='part'` files with rich metadata, Assembly Components reference Parts, BOM rollup endpoint + CSV export, per-Part `visibility` (private/unlisted/public), photos via `users/<uid>/avatar.jpg`-pattern Storage layer, verified-publisher flag (`users.is_verified_publisher` + blue-check badge across Workshop / WorkshopListing / LibraryPicker / Library cards), workshop "Verified" filter chip, BOM Phase 1+2+3 surface UX (notes + MOQ + Lead + U.Price + Alternates). KiCad-style for both mech and electronics. |
| **Library Phase 2: distributor APIs** | ✅ shipped | Live pricing + stock for DigiKey (OAuth2), Mouser, LCSC; McMaster stub. Encrypted credentials in `distributor_credentials`, `distributors.Registry` per-provider rate limits, `ErrAuth` / `ErrRateLimit` / `ErrNotSupported` sentinels for the admin UI. Boot-time sweep refreshes stale Part entries every 6h; per-Part "Refresh prices" button via `RefreshPart`. HTTP surface: admin `GET/PUT/DELETE /api/admin/distributors[/{name}]` + per-Part `POST /api/projects/{pid}/files/{fid}/distributors/refresh`. Tests in `cmd/test/scenarios/distributors.go` use `http.RoundTripper` mocks (no live distributor traffic). |
| **Library Phase 3: curated manufacturer libraries** | ✅ shipped | Verified-publisher accounts, Workshop badge, manufacturer-contributed updates via PR. Workshop "Verified" filter chip + blue-check badge shipped (Workshop, WorkshopListing, LibraryPicker). Seed publisher shipped: `seed/publishers/parts/*.json` + `npm run seed:publishers` populates a `kerf-system`-owned `Common Components` example library. v1 is a demonstration set (3–5 parts). Manufacturer-PR submission flow shipped: `POST /api/library/submissions` (any auth user), admin-only `GET/PUT /api/admin/library/submissions[/{id}]` for review queue, frontend modal on /library. Approved submissions create new public Parts in the target Library workspace. |
| **Library as its own top-level area (split from Workshop)** | ✅ shipped | Phase 1 shipped: `src/routes/Library.jsx` (new) renders parts catalog (search + category chip + verified filter) reusing `GET /workshop/parts` endpoint. Linked from top nav. Phase 2 shipped: canonical `GET /api/library/parts` endpoint (alias of `/workshop/parts`); `LibraryPicker.jsx` and `Library.jsx` consume the new endpoint via `library.listParts`. `workshop.listParts` kept as a deprecated alias. Phase 3 shipped: `/library/{slug}` part detail route renders header + photo + distributors + 'Use in Assembly' CTA. Inline `DetailsPanel` retained as fallback. Phase 4 shipped: `GET /api/library/parts/{slug}` returns part-detail JSON; `LibraryPart.jsx` consumes it instead of getting a 404. The full `/library` split (Phases 1–4) is now end-to-end. |
| **BOM UX rework** | ✅ shipped | All BOM Phase 1+2+3 surface UX shipped: notes + MOQ + Lead + U.Price + Alternates. Notes editable in `BOMTable`; distributor metadata surfaced read-only from the cheapest distributor entry (via `pickCheapestDistributor`); Alternates column lists every other distributor on the part as compact `<name> <price>` pills sorted ascending, capped at 3 with `+N more` overflow tooltip (via `pickAlternates`). |
| **Electronics objects/features fix** | ✅ shipped | `CircuitObjectsPanel.jsx` renders Components (refdes + ftype + engineering-notation values) and Nets (union-find over `source_trace.connected_source_port_ids`, GND auto-labeled). Library-link chips persist via `setCircuitLibraryMapping`; bidirectional highlight panel↔schematic via `selectedCircuitComponentId`. 3D tab substitutes real geometry for Library-mapped `cad_component`s: `evalLibraryModel3D` runs the Part's `model_3d` JSCAD source through `runJscad` (lazy-imported); two-layer cache (`fetchCacheRef` for fileId-keyed dedup, `libraryGeoms` for the splice surface); 4 try/catch boundaries fall through to the existing teal "linked" box on any failure. STEP-string `model_3d` fields fall through to the box pending a STEP parser. |
| **LLM tool consolidation (doc-search + small fixed surface)** | ✅ shipped | ~30 domain-specific tools collapsed into a small fixed surface (file ops, object ops, BOM, validation, four `create_*` scaffolders) plus `search_kerf_docs` over an embedded markdown corpus under `packages/kerf-chat/llm_docs/` (and per-plugin `llm_docs/` dirs). The model reads the relevant doc page and edits the file's JSON / TSX directly via `write_file` / `edit_file`. Adding a new domain is a markdown change, not a code change. |
| **Chat panel collapsible** | ✅ shipped | Topbar `PanelRightClose/Open` button toggles the entire 380px column away — center main expands. State persisted to `localStorage`. |
| **User avatars + CDN-backed images** | ✅ shipped | `users.avatar_storage_key` column (migration `1746576600000_user_avatar_storage.sql`). `POST /api/me/avatar` (multipart re-encodes JPEG q=85, stores at `users/<uid>/avatar.jpg`), `DELETE /api/me/avatar` for clearing. Google-OAuth-triggered avatar pull on first login. Storage abstraction with `CDNBaseURL` for cloud (bunny.net Pull Zone) vs local-via-blobs. |
| **Workspaces (orgs) — multi-member containers** | ✅ shipped | `workspaces` + `workspace_members` tables (migration `1746577400000_workspaces.sql`); projects carry `workspace_id`; routes mounted under `/w/:workspaceSlug/{projects,settings,members}`. UI: `WorkspaceSwitcher` in the layout, `WorkspaceSettings` page (rename, slug, avatar), `WorkspaceMembers` (invite + role change). Cloud billing attaches to workspace via Paystack. Remaining nit: the internal `useWorkspace` zustand store still uses that name — renaming to `useEditor` is a non-trivial cross-component refactor and is deliberately deferred. |
| **Project change timeline (with avatars)** | ✅ shipped | `GET /api/projects/:pid/activity` (handler in `internal/handlers/activity.go`) merges file_revisions + chat_messages + project mutations. `ActivityTimeline.jsx` with day-grouped feed + source-typed avatars. Surfaced in the Editor's right-panel slot (`rightPanel === 'activity'`); avatars resolved via `users.avatar_storage_key`. |
| **Rhino parity: NURBS surface depth** | ✅ shipped | surfacing.py + .surf docs + sweep/network/blend tools shipped. |
| **Rhino parity: 3DM file format** | ✅ shipped | `packages/kerf-imports/src/kerf_imports/rhino3dm_route.py` + `packages/kerf-imports/src/kerf_imports/tools/import_3dm.py` + `src/lib/rhino3dm.js` + import_3dm.md shipped. |
| **Rhino parity: SubD modeling** | ✅ shipped | `packages/kerf-imports/src/kerf_imports/tools/subd.py` + `src/lib/subd.js` + `.subd` file kind + Catmull-Clark + 044 migration shipped. |
| **Rhino parity: layers + display modes** | ✅ shipped | Already shipped earlier as project-layers ('.canvas.json' + ProjectLayersPanel.jsx + project_layers.py). |
| **Rhino parity: mesh tools** | ✅ shipped | `packages/kerf-imports/src/kerf_imports/tools/mesh.py` + `src/lib/meshTools.js` + 044 migration shipped. |
| **Rhino parity: parametric graph (Grasshopper-equivalent)** | ✅ shipped | `packages/kerf-imports/src/kerf_imports/tools/graph.py` + `src/lib/graph.js` + `graphOps.js` + `.graph` file kind + `GraphEditor.jsx` shipped. |
| **Rhino parity: render-quality output** | ✅ shipped | `packages/kerf-render/src/kerf_render/routes.py` + `packages/kerf-render/src/kerf_render/tools.py` + `src/lib/render.js` + `.render` file kind shipped. |
| **Rhino parity: drafting completeness** | ✅ shipped | `src/lib/draftingComplete.js` + drafting completeness shipped (hatch, leaders, rich text, dim chains). |
| **Rhino parity: curve depth** | ✅ shipped | `src/lib/curveOps.js` + `packages/kerf-imports/src/kerf_imports/tools/curve_ops.py` shipped (12 ops). |
| **Revit parity: categories + hosted refs** | ✅ shipped | `src/lib/bimCategories.js` + `packages/kerf-bim/src/kerf_bim/tools/bim_categories.py` shipped. |
| **Revit parity: type vs instance params** | ✅ shipped | Covered by family.py + element_types.py. |
| **Revit parity: `.family.json` parametric components** | ✅ shipped | `packages/kerf-bim/src/kerf_bim/tools/family.py` + `src/lib/family.js` + 037 migration shipped. |
| **Revit parity: `.schedule.json` live queries** | ✅ shipped | `packages/kerf-bim/src/kerf_bim/tools/schedule.py` + `src/lib/schedule.js` + 038 migration shipped. |
| **Revit parity: `.view.json` derived views** | ✅ shipped | `packages/kerf-bim/src/kerf_bim/tools/view.py` + `src/lib/view.js` + 039 migration shipped. |
| **Revit parity: `.sheet.json` print-ready layouts** | ✅ shipped | `packages/kerf-bim/src/kerf_bim/tools/sheet.py` + `src/lib/sheet.js` + 039 migration shipped. |
| **Revit parity: phasing + filters** | ✅ shipped | `src/lib/phasing.js` + `src/lib/viewFilters.js` shipped. |
| **Revit parity: stairs + railings** | ✅ shipped | `packages/kerf-bim/src/kerf_bim/tools/stairs.py` + `railings.py` + 041 migration shipped. |
| **Revit parity: MEP routing** | ✅ shipped | `packages/kerf-bim/src/kerf_bim/tools/mep.py` + `src/lib/mep.js` + 040 migration shipped. |
| **Revit parity: curtain wall** | ✅ shipped | `packages/kerf-bim/src/kerf_bim/tools/curtain_wall.py` + `src/lib/curtainWall.js` + 042 migration shipped. |
| **Schematic + PCB editor depth** | ✅ shipped | Manual trace routing + copper pours + layer stack + LayersPanel + DRC overlay all shipped + wired into PCBView. |
| **FreeCAD parity: PartDesign feature depth** | ✅ shipped | feature_helix.py, feature_draft.py, feature_mirror.py, feature_multi_transform.py, feature_rib.py all shipped. |
| **FreeCAD parity: Sketcher constraint depth** | ✅ shipped | `src/lib/sketchCarbonCopy.js` + `sketchValidate.js` + `packages/kerf-cad-core/src/kerf_cad_core/sketch.py` extensions shipped. |
| **FreeCAD parity: sketch → 3D shortcuts** | 🔮 planned | Sketch-based features that take an in-place sketch and a body and apply an op in one step (FreeCAD's "active body" model). Full design doc: [`docs/plans/freecad-sketch-shortcuts.md`](./docs/plans/freecad-sketch-shortcuts.md). Five sub-tasks split out below (3 new LLM tools + 2 flag extensions on existing tools); est. ≈4 sonnet-agent-days total, parallelisable. |
| ↳ **`feature_boss_with_draft`** | ✅ shipped | Pad + draft in one node. OCCT: `BRepPrimAPI_MakePrism` then per-side-face `BRepOffsetAPI_DraftAngle` with neutral plane = sketch plane. Schema: `{sketch_path, height, direction, draft_angle_deg ∈ [-30,30], draft_direction}`. Worker handler `opBossWithDraft` + `walkSideFaces` helper wired in both dispatch switches. Frontend: `boss_with_draft` entry in `FEATURE_KINDS` slotted after `pad` in the `sketch` category. LLM doc at `kerf-chat/llm_docs/feature_boss_with_draft.md`. |
| ↳ **`feature_cut_from_sketch`** | ✅ shipped | Subtract a sketched region from any planar face of a target body, normal to that face (unlike `pocket` which cuts normal to the sketch plane). OCCT: `faceById` + `faceFrame` → `placeFaceOnPlane(face-anchored)` → `BRepPrimAPI_MakePrism(-normal*depth)` → `BRepAlgoAPI_Cut_3`. Schema: `{target_id, target_face_id, sketch_path, depth, reverse}`. Worker handler `opCutFromSketch` wired in both dispatch switches. Shares `push_pull`'s face-id stability caveat (Phase 4 persistent-naming fixes). LLM doc at `kerf-chat/llm_docs/feature_cut_from_sketch.md`. |
| ↳ **`feature_hole_pattern_from_sketch`** | ✅ shipped | Parametric `hole_pattern` op references a sketch carrying point entities; worker iterates at eval time and runs N cylinder cuts via shared `cutCylinderAtPoint` helper (refactored out of `opHole`). Schema: `{target_id, sketch_path, diameter, depth}`. Non-point entities silently ignored. `opHolePattern` + `parseSketchPoints` wired in both dispatch switches. FeatureView entry after `hole`. 47 pytest + 28 vitest pass. LLM doc at `kerf-chat/llm_docs/feature_hole_pattern_from_sketch.md`. |
| ↳ **Loft `symmetric` flag (mid-plane)** | 📋 next | Extend `feature_loft` with `symmetric: true` — `opLoft` mirrors both profiles across the mid-plane and feeds `[p1, p2, p2', p1']` to `BRepOffsetAPI_ThruSections` for a thin-walled symmetric body. Limited to exactly 2 input profiles; non-parallel sketch planes → `BAD_ARGS`. No new tool, no new op — flag on existing infra. ≈0.5 sonnet-days. |
| ↳ **Sweep1 `mode` flag (tangent-locked)** | ✅ shipped | `mode: "auto"\|"frenet"\|"corrected_frenet"` added to `feature_sweep1` schema + handler; worker `SetMode_5` path confirmed; FeatureView inspector already had the select; LLM doc + pytest schema tests + vitest coil-path frame-orientation tests landed. |
| **Sketch → JSCAD workflow (mesh-side analog of `.feature`)** | 🔮 planned | Constrained 2D `.sketch` with dimensions → AI-generated `.jscad` 3D part. Sketch stays the source of truth — editing a sketch dimension reflows the 3D. JSCAD route picked when STEP/BRep/fillets aren't required (no OCCT WASM, infinite programmability, mesh-cheap booleans). New `extrude_sketch_to_jscad` LLM tool scaffolds the file with the canonical `import profile from '/x.sketch'` shape (already wired in `jscadRunner.js`). See [docs/plans/sketch-to-jscad.md](docs/plans/sketch-to-jscad.md) for full design + 5-task breakout. |
| ↳ Document the working sketch-import form in `llm_docs/jscad.md` | ✅ shipped | Rewrote `packages/kerf-chat/llm_docs/jscad.md`: canonical `export default function ({ primitives, … })` shape, ES `import profile from '/x.sketch'` (matched against runtime's `SKETCH_IMPORT_RE`), `.equations` → `params` injection section, `.jscad` vs `.feature` comparison table, complete worked example. Anti-patterns explicitly forbid `require()`. |
| ↳ Implement `extrude_sketch_to_jscad` LLM tool | ✅ shipped | New Python tool in `kerf-cad-core/extrude_sketch_to_jscad.py`. Validates sketch exists + parses to ≥ 1 closed loop, then emits canonical `.jscad` source per op (`extrude_linear` / `extrude_rotate` / `sweep_along_path`). Uses `extrudeFromSlices` for sweeps (verified: no `sweepAlong` in `@jscad/modeling` 2.x). 60 pytest tests — all green. LLM doc at `packages/kerf-chat/llm_docs/extrude_sketch_to_jscad.md`. |
| ↳ Surface sketch-import errors in JSCAD viewport | ✅ shipped | `resolveSketchImports` now throws `sketch not found: /path — available sketches: [...]` instead of falling back to an empty Geom2. `runJscad` catches the throw and returns `{ error }`. The viewport renders a red overlay banner when `partsError` is set. `setSketchLister` added so the error message lists the project's `.sketch` files. |
| ↳ Reactive re-eval when an imported sketch changes | ✅ shipped | `updateSketch` now calls `_reEvalJscadForSketch` after persisting; `sketch_*` LLM tools added to `FILE_MUTATING_TOOLS` so `sendMessage` triggers `loadFileForEditor` (which re-runs `runJscad`). `SKETCH_IMPORT_RE` exported from `jscadRunner.js` for shared parse. Vitest coverage in `src/__tests__/jscadReactiveReEval.test.js`. Cross-file graph invalidation (assembly → jscad → sketch) deferred. |
| ↳ "Build 3D" SketchView affordance + file-tree backlink | 📋 next | SketchView toolbar dropdown — Extrude → / Revolve → — invokes `extrude_sketch_to_jscad` and opens the new file. File-tree row renders a subtle "← <sketch-name>" chip on `.jscad` files that import a sketch. |
| **FreeCAD parity: Draft workbench (2D CAD)** | ✅ shipped | `packages/kerf-imports/src/kerf_imports/tools/draft.py` + `src/lib/draft.js` + 045 migration shipped. |
| **FreeCAD parity: inspection / model comparison** | ✅ shipped | `packages/kerf-imports/src/kerf_imports/tools/inspection.py` + `src/lib/modelCompare.js` shipped. |
| **KiCad parity: hierarchical schematics** | ✅ shipped | `packages/kerf-electronics/src/kerf_electronics/tools/hier_schematic.py` + `src/lib/hierSchematic.js` shipped. |
| **KiCad parity: buses + differential pairs** | ✅ shipped | `packages/kerf-electronics/src/kerf_electronics/tools/buses.py` + `src/lib/buses.js` shipped. |
| **KiCad parity: net classes + design rules** | ✅ shipped | `packages/kerf-electronics/src/kerf_electronics/tools/net_classes.py` + `src/lib/netClasses.js` shipped. |
| **KiCad parity: length tuning + match** | ✅ shipped | `packages/kerf-electronics/src/kerf_electronics/tools/length_tuning.py` + `src/lib/lengthTuning.js` shipped. |
| **KiCad parity: via stitching + teardrops** | ✅ shipped | `packages/kerf-electronics/src/kerf_electronics/tools/via_stitching.py` + `src/lib/viaStitching.js` shipped. |
| **KiCad parity: push-pull interactive routing** | ✅ shipped | `packages/kerf-electronics/src/kerf_electronics/tools/shove_router.py` + `src/lib/shoveRouter.js` shipped. |
| **KiCad parity: electrical rules check (ERC)** | ✅ shipped | `packages/kerf-electronics/src/kerf_electronics/tools/erc.py` + `src/lib/erc.js` + frontend wiring in CircuitObjectsPanel shipped. |
| **KiCad parity: per-pad mask/paste overrides** | ✅ shipped | `packages/kerf-electronics/src/kerf_electronics/tools/pad_overrides.py` + `src/lib/padOverrides.js` shipped. |
| **Docs: ROADMAP + restructured /docs + landing revamp** | ✅ shipped | `docs/index.md` TOC, `docs/whats-new.md` sprint summary, 8 stale ROADMAP labels flipped, `build-docs-manifest.mjs` updated with new entries, Landing hero revamped with "open source · now shipping IFC" badge and whats-new link. |

Legend: ✅ shipped · 🚧 in flight · 📋 next · 🔮 planned (multi-quarter)

---

## Modeling philosophy: two coexisting paradigms

Kerf supports **two kernels in one project**, picked per-file:

```
.jscad      → JSCAD code → mesh                (cheap, scriptable, ~one sprint to ship features)
.feature    → feature tree → OCCT BRep → mesh  (precise, exports STEP losslessly, real fillets)
.sketch     → planegcs Geom2 profile           (consumed by either)
.assembly   → Components ref any 3D file kind  (kernel-agnostic)
.drawing    → projects views from any 3D       (kernel-agnostic)
```

A project can mix both styles. Operations *within* a `.feature` file run at
full B-rep fidelity; operations *across* `.feature` and `.jscad` files
(assemblies, CSG mixes) work at mesh level — same trade Rhino/FreeCAD make.

Why both? Code-first is unbeatable for parametric exploration with the
chat-LLM in the loop; B-rep is unbeatable for engineering-precision output and
features the mesh world can't deliver (precise fillets, lossless STEP export,
edge identity for selection-based ops).

---

## Parametric foundation: equations + configurations

Both can ship in parallel with Phase 2/3 — no kernel dependency. They
are the layer that turns kerf from "a tool that draws shapes" into "a
tool that captures parametric intent." Outsized leverage for the LLM:
a model that can edit a JSON parameter table fluently is a model that
can drive parametric exploration in chat.

### Equations: project-level named parameters

New file kind `.equations` — JSON map of named values:

```
{
  "wheel_diameter": { "value": 120, "unit": "mm", "description": "outer rim" },
  "wheel_radius":   { "expression": "wheel_diameter / 2", "unit": "mm" },
  "spoke_count":    { "expression": "ceil(wheel_diameter / 20)", "unit": "scalar" }
}
```

- **Expression eval:** [mathjs](https://mathjs.org/) (MIT). Numeric only — no symbolic CAS.
- **Resolution:** topological sort by dependency, cycle detection, evaluate.
- **Injection:** the resolved `params` object reaches every file eval.
  JSCAD worker exposes it on the eval scope (`params.wheel_diameter`).
  `.feature` JSON values can be either literals or expression strings
  (`"wheel_diameter / 4"`). `.sketch` constraint dimensions can
  reference parameter names.
- **Units:** declared per parameter; surfaces in drawing dimensions
  ("Ø120mm"). Optional in v1 — default scalar/length-mm.
- **LLM tool:** `set_parameter({ name, value | expression, unit?, description? })`.
  Model can also `edit_file` the `.equations` JSON directly. Doc page at
  `packages/kerf-chat/llm_docs/equations.md`.

### Configurations: per-file variants

Schema, on any file that opts in:

```
configurations: {
  active: "M4",
  configs: {
    "M3": { diameter: 3, thread_pitch: 0.5, head_diameter: 5.5 },
    "M4": { diameter: 4, thread_pitch: 0.7, head_diameter: 7   },
    "M5": { diameter: 5, thread_pitch: 0.8, head_diameter: 8.5 },
    "M6": { diameter: 6, thread_pitch: 1.0, head_diameter: 10  }
  }
}
```

- **Eval pipeline:** `defaults → project equations → active config overrides → file body uses final values`.
  Configs are just an override layer on top of the same expression evaluator equations use.
- **Editor:** config dropdown at the top of any file with configurations.
  Switching re-evals viewport and any open drawings.
- **Assembly references:** Component rows gain a `config` field — "this
  instance uses the M4 config". BOM rollup groups by `(file_id,
  config_id)` so 4×M3 + 2×M4 bolts show as two BOM lines.
- **Insert dialog:** picking a Part exposes its configuration list;
  default is the file's `active`.
- **Library impact:** Parts surface their config list in the Library
  picker — "M-series cap screw" shows as one Part with M3/M4/M5/M6
  configs, not four separate Parts. This was always the right shape
  for libraries; it only becomes possible once configurations exist.
- **LLM tools:** `add_configuration({ file, name, overrides })`,
  `set_active_configuration({ file, name })`. Doc page at
  `packages/kerf-chat/llm_docs/configurations.md`.

### Phasing

- **E1.** `.equations` file kind, mathjs expression eval, project-level
  params injected into JSCAD + `.feature` eval, sketch dimensions can
  reference parameter names. (Equations alone — no configs yet.)
- **C1.** Per-file configurations (parameter overrides), editor
  dropdown, assembly Component config selection, BOM groups by `(file, config)`,
  Library Parts expose configs in the picker.
- **E2 / C2.** Drawing dimensions display parameter names alongside
  values ("width = 100mm"). Insert-dialog config preview thumbnails.
- **E3 / C3.** Cross-project parameter inheritance — a master assembly
  project defines parameters, sub-projects pull from it. Depends on
  cross-project Component refs landing first.

### Non-goals

- **Symbolic math / CAS.** mathjs is numeric; that's enough.
- **Parameter optimization** ("find values that minimize this
  objective"). Tier 1 advanced capability later.
- **Config-specific feature suppression** ("delete this fillet for the
  M3 config but keep it for M4"). Error-prone even in SolidWorks; punt.
- **Auto-generated config tables** ("create M3 through M30 stepping by
  1"). Punt to the scripting layer.

---

## Scripting: `.script.py` automation via `kerf-sdk`

The FreeCAD-Python equivalent — user-written code that drives the
project — built around the language Kerf's target users already know
(engineers live in Python: numpy, scipy, cadquery, build123d,
opencamlib, scikit-rf). It's also a force multiplier *for* the LLM:
the model can write a one-shot script when no fixed tool exists for
the job, run it, see the result, and discard it.

### Language: Python (with the door open for others)

Runtime is the **user's own Python** — their laptop, their CI, their
internal server. Kerf publishes `kerf-sdk` to PyPI (MIT-licensed);
users `pip install kerf-sdk`, write `.script.py` files, and talk to a
Kerf instance over HTTP/JSON-RPC.

Reasons Python over TypeScript:

- Target users (engineers) live in Python and the ecosystem is the
  whole point — cadquery, build123d, scipy, opencamlib, scikit-rf,
  FreeCAD bindings. None of these exist in JS.
- Running on the user's machine sidesteps every sandbox /
  multi-tenancy / deploy problem. No Firecracker, no warm pools, no
  Python runtime to bundle into the single-binary install.
- Users get their own IDE, type checker (pyright), debugger, package
  manager. We don't have to ship in-app development tooling.
- Heavy compute is the user's hardware, not Kerf's per-tenant compute
  budget.

**The architecture is language-agnostic at the contract layer.** The
RPC contract is a versioned OpenAPI spec under `/v1/`; `kerf-sdk` is
the first binding. TypeScript / Lua / Go / Rust bindings can be
generated from the same spec when users ask — one week per binding,
paid only when demand is real. We're not betting Python; we're betting
Python *first*.

### Architecture: external execution, HTTP/JSON-RPC, fixed backend ops

The hard rule stays the same: **the Kerf backend never executes user
code in v1.** Only fixed, audited Go-implemented operations run
server-side. User code lives on the user's machine and calls the
backend over HTTP.

```
┌─ User's machine ────────────────────────┐    ┌─ Kerf backend ─────┐
│  Python 3.11+                           │    │  (local OR cloud)  │
│  ├─ pip install kerf-sdk                │    │                    │
│  ├─ user's IDE / debugger / pyright     │    │                    │
│  └─ scripts/regen-all.script.py         │    │                    │
│        │  uses kerf.*                   │    │                    │
│        ▼                                │    │                    │
│  kerf.files.read()       ──HTTP─────────┼───►│ /v1/files/...      │
│  kerf.equations.set()    ──HTTP─────────┼───►│ /v1/equations/...  │
│  kerf.fem.run()          ──HTTP─────────┼───►│ /v1/fem/run        │
│  kerf.cam.toolpath()     ──HTTP─────────┼───►│ /v1/cam/toolpath   │
└─────────────────────────────────────────┘    └────────────────────┘
```

The backend exposes the *same* registry the LLM tool surface already
uses — one source of truth, two callers (LLM + user scripts). Adding
a new heavy op makes it usable from both surfaces at once. The RPC
spec lives under `/v1/` so v2 can coexist when shapes evolve.

A future hosted execution mode ("Run on Kerf compute" for cloud users
who don't want a local Python install) becomes an alternative endpoint
that wraps the same RPC contract — not a redesign. Sandbox engineering
(Firecracker or per-workspace container) is real work, deferred until
a customer asks.

### File kind: `script` (extension-discriminated)

The kind in the file table is generic `script` with an `extension`
field, so `.lua` / `.ts` / `.js` can join later without a migration —
data, not enum. v1 ships `.script.py` only.

```
project/
  ├── parts/wheel.feature
  ├── assemblies/main.assembly
  ├── parameters.equations
  └── scripts/
        ├── regen-all-steps.script.py
        ├── batch-rename-parts.script.py
        └── validate-bom.script.py
```

A script imports `kerf-sdk`:

```python
from kerf import client

kerf = client.from_env()  # local install token or KERF_API_TOKEN

for wheel_d in [80, 100, 120, 140]:
    kerf.equations.set("wheel_diameter", wheel_d)
    result = kerf.fem.run(
        source_file="parts/wheel.feature",
        materials=[{"id": "AL-6061", "E": 69e9, "nu": 0.33, "rho": 2700}],
        fixtures=[{"face_ref": "hub_inner", "type": "fixed"}],
        loads=[{"face_ref": "rim", "type": "pressure", "magnitude": 1e5}],
        studies=["static"],
    )
    print(f"d={wheel_d} -> max von Mises = {result.max_von_mises} Pa")
```

Editor surface: `ScriptEditor` renders `.script.py` as a Python
read-only viewer in v1; the kerf web UI shows the script file's
current state + history. Users edit their scripts in their own IDE.
In-app Monaco + pyright LSP is a v1.5 polish, not a blocker.

A `kerf` CLI ships with the SDK for the run loop: `kerf run script.py`,
`kerf ls`, `kerf push`, `kerf diff`. Or users skip the CLI and just
`python script.py` — the SDK works as a plain library.

### `kerf.*` API surface (v1)

The Python surface mirrors the JSON-RPC contract 1:1; the contract
itself is the existing LLM tool registry plus minimal script-specific
helpers (batch reads, streaming events for long ops) added reactively.
The SDK is generated from the OpenAPI spec so Python and contract
never drift.

**Read:**
- `kerf.files.list()`, `kerf.files.read(path)`, `kerf.files.history(path)`
- `kerf.equations.read()`, `kerf.equations.get(name)`
- `kerf.assemblies.read(path)`, `kerf.bom.compute(assembly_path)`
- `kerf.config.list(file_path)`, `kerf.config.get(file_path, name)`

**Mutate** (every mutation routes through `file_revisions`, so undo /
branch / git-sync work the same as for human edits):
- `kerf.files.write(path, content)`, `kerf.files.delete(path)`
- `kerf.equations.set(name, value_or_expr)`, `kerf.equations.delete(name)`
- `kerf.config.set(file_path, name, overrides)`, `kerf.config.activate(file_path, name)`
- `kerf.feature.run(file_path, op, params)`

**Heavy (RPC, polled or streamed):**
- `kerf.fem.run({...})` → resolves with summary + result-file ID
- `kerf.cam.toolpath({...})` → same pattern (lights up when CAM
  is no longer a stub)
- `kerf.step.tessellate({...})` → same pattern (lights up with the
  perf phase)

Each `kerf.*` call has a 1:1 entry in the backend RPC registry; the
same registry powers the LLM tool surface.

### Phasing

- **S1.** Generic `script` file kind with `extension` field (replaces
  the earlier `.script.ts` Phase 1 stub), OpenAPI 3.x spec for the
  existing LLM tool registry under `/v1/` namespace, `kerf-sdk`
  skeleton on PyPI with auth + read-only API + `kerf` CLI,
  `ScriptEditor` renders Python read-only, one end-to-end example
  script.
- **S2.** Full mutation API in the SDK (`write_file`, `set_parameter`,
  `set_configuration`, `run_feature`). Mutations flow through
  `file_revisions` so undo / branches / git-sync work uniformly.
- **S3.** Heavy-op SDK bindings (`kerf.fem.run`, `kerf.cam.toolpath`,
  `kerf.step.tessellate`). Long-poll / streaming-events plumbing
  shared across all heavy ops; new heavy ops register a backend handler
  + an OpenAPI spec addition + auto-generated SDK method.
- **S4.** Long-running script lifecycle: progress reporting, structured
  cancellation, run history, scheduled runs (cron) on the cloud tier
  via a webhook the user's CI can call.
- **S5 (optional, demand-gated).** Hosted execution: "Run on Kerf
  compute" button uploads the script + executes in a per-workspace
  sandbox. Same SDK, same contract, different runner location.
- **S6 (optional, demand-gated).** Second-language bindings — TypeScript
  / Lua / Go via the same OpenAPI spec. ~One week per binding, paid only
  when demand is real.

### Dependencies

- **Equations + configurations** are landed and are the most-natural
  first targets for script automation. ✅
- **OpenAPI spec for the LLM tool registry** is the gating piece — S1
  doesn't ship until the contract is formalized.
- **Heavy-op SDK methods light up as their backend features land** —
  `kerf.fem.run` when FEM workers exist, `kerf.cam.toolpath` when CAM
  is real (currently stub, see CAM Phase 1 row). S3 is incremental,
  not a single ship.

### Non-goals (v1)

- **Backend execution of user code (v1).** User runs Python on their
  machine. Hosted execution is an explicit S5, demand-gated.
- **Plugin marketplace.** Scripts are per-project files,
  version-controlled with the project. No global install or app-store.
- **In-app debugger.** Users use pyright + their IDE. We ship
  structured errors + stack traces back over HTTP; that's it.
- **Custom feature types via scripting.** Tempting but couples
  scripting to the kernel; punt to a separate "user feature" plan.
- **Synchronous browser execution.** The "drag a slider, see the part
  update" use case is served by the existing JSCAD / planegcs paths,
  not by scripts. Scripts are for automation, not for in-loop UI
  reactivity.

---

## Phase 2: `.feature` files + OCCT integration

The next big swing. Detailed plan:

### Scope
- New file kind `feature`. JSON-encoded feature tree on disk; OCCT BRep at runtime.
- WASM worker bundling [opencascade.js](https://github.com/donalffons/opencascade.js) (~7-15 MB, lazy-loaded).
- Initial feature set: Pad, Pocket, Revolve, Loft, Sweep, Fillet, Chamfer, Shell, Draft, Hole.
- Tessellation pipeline: BRep → triangulated mesh for renderer; preserves face/edge IDs for selection.
- LLM tools: `feature_pad`, `feature_pocket`, `feature_fillet`, etc. — each a structured edit on the feature tree.
- STEP/IGES export at B-rep precision (replaces the current mesh-export STEP).
- `.feature` files render in the same Editor as `.jscad`, but the chat tools, Object panel, and feature panel switch behavior based on the file kind.

### Open questions
- Feature tree representation: array of {op, params, refs} vs. linked list with explicit dependency edges. Likely the simpler array.
- Edge/face references inside the tree: persistent across edits is *the* hard problem. OCCT's `BRepTools::Substitution` + naming heuristics. We'll start with simple sha-based IDs and iterate.
- Mesh ↔ BRep bridge for cross-kernel ops in assemblies.

### Non-goals (Phase 2)
- Direct modeling (push/pull). That's Phase 3.
- NURBS surfacing tools beyond what OCCT exposes for free. Phase 4.
- Real-time multi-user editing. Different project entirely.

---

## Phase 3: Direct modeling + viewport selection

After `.feature` lands and stabilizes:
- Click an edge/face in the 3D viewport → it becomes a reference.
- "Push/pull this face" — direct-edit moves on top of the feature tree.
- Sketch on a face (place the sketch's plane on a real face of an existing body).
- Pattern features (linear, polar, mirror).

---

## FEM: mechanical analysis (post-Phase 3)

Finite element analysis as a first-class mechanical capability.
Chat-driven "make this part, run FEM, report the factor of safety" is
the demo that justifies a chat-LLM CAD tool over traditional GUIs.

### Stack

- **Solver: FEniCSx** (LGPL3, Python-native) — modern, actively developed
  by a UK/US research consortium funded through 2027+. UFL (Unified Form
  Language) makes coupled multiphysics first-class and forms are
  **differentiable** — which makes topology optimization, inverse
  problems, and future ML-CAD integration land cleanly without separate
  optimization wrappers. GPU acceleration on roadmap. Python-native fit
  with `pyworker` (no subprocess wrangling).
- **Mesher: Gmsh** (GPL2, Python bindings) — de facto OSS mesher; same
  in either solver branch.
- **Second solver: CalculiX** (GPL2) — kept as a documented future
  alternative behind the same `pyworker` `/run-fem` route via an
  optional `solver` field. Lands when demanded — typically for
  FreeCAD-bit-exact behavior parity or frictional-contact workloads
  where CalculiX's polish currently exceeds FEniCSx's. Migration
  surface: one Python module in `pyworker`; no API or schema changes.
- **License posture:** FEniCSx is LGPL3; HTTP boundary via `pyworker`
  keeps Kerf core MIT. CalculiX (GPL2) when added uses the same HTTP
  boundary pattern. Neither solver linked into the MIT kerf binary.
  Both run inside the cloud-tier `pyworker` service; OSS users who
  want server-side FEM run `kerf-pyworker` themselves locally.
- **Why FEniCSx over CalculiX as primary:** CalculiX's strengths (deep
  element variety, mature frictional contact, Abaqus-style `.inp`
  format) are real but locked to a near-static legacy codebase. FEniCSx
  is where the modern FEM frontier lives — multiphysics, GPU,
  differentiable, AMR. For a CAD tool that wants to grow into
  thermal-structural / FSI / topology opt / ML-aware design in the
  3-5-year horizon, the modern stack wins. CalculiX stays available
  for the specific cases where it leads, behind the same seam.

### Data model

New file kind `.fem` — JSON study spec referencing a 3D source file
the way `.drawing` already does:

```
.fem → {
  source_file_id, source_revision_id?,
  mesh:      { size, type: "tet" | "hex_dominant" },
  materials: [{ id, E, nu, rho, ... }],
  fixtures:  [{ face_ref, type: "fixed" | "slider" | "pinned" }],
  loads:     [{ face_ref, type: "force" | "pressure" | "torque", magnitude, direction }],
  studies:   ["static", "modal", ...],
  solver_opts
}
```

Results are derived artifacts keyed by `(source_revision_id,
fem_revision_id)` — same caching pattern as the planned STEP
pre-tessellation cache. Stored: deformed mesh, per-element stress
tensor, modal frequencies + mode shapes, summary JSON (max stress, FoS).

### F1 scope (first ship)

- **Linear static** — forces, pressures, fixed/sliding/pinned faces,
  isotropic materials. Output: von Mises, displacement, factor-of-safety.
- **Modal** — first N natural frequencies and mode shapes (almost free
  on top of linear static).
- **Bonded contact in assemblies** — multi-body studies, parts tied at
  touching faces. No friction yet.
- **Compute targets:** cloud-tier `pyworker` (`/run-fem` route) for
  hosted users; optional self-hosted `kerf-pyworker` for OSS users
  who want server-side FEM locally. Same job spec either side.
- **Renderer:** stress-colored mesh with displacement-scale slider;
  mode-shape playback for modal results.
- **LLM tool:** single `fem_run({ source_file, materials, fixtures,
  loads, studies, mesh_size })` returning max stress, max displacement,
  FoS, modal frequencies, and a result-file ID. Doc page at
  `packages/kerf-chat/llm_docs/fem.md` per the consolidated tool pattern.

### Dependencies

Sits after Phase 3 (viewport face selection). Realistic boundary
conditions need stable face references on a B-rep — only `.feature`
files have those — and the BC-picking UX needs viewport face-clicking.
A `.jscad` fallback (faces by normal/region) is possible later, not v1.

### Phase ordering inside FEM

- **F1.** Linear static + modal + bonded contact, local + cloud
  workers, single LLM tool.
- **F2.** Frictionless contact, multi-step loading, anisotropic materials.
- **F3.** Thermal + thermal-mechanical (natural in FEniCSx via UFL coupled forms; no second solver needed).
- **F4.** Frictional contact, plasticity / hyperelastic, dynamic
  implicit/explicit. Multi-quarter; only with demand.

### Non-goals

- CFD — different solver, different culture; far future under a
  separate flow-simulation file kind.
- In-browser solver. MFEM-WASM is interesting, but real solves take
  seconds-to-minutes; server roundtrip is not the bottleneck. The
  `.fem` spec is solver-agnostic so a WASM backend can drop in later
  without data-model changes.
- Topology optimization — adjacent but separate workflow.

---

## Mechanical advanced capabilities (Tier 1)

A grouped cluster of mechanical-CAD-grade features that ship after the
parametric foundation + Phase 2/3 are in. Each follows the FEM pattern
— minimal v1, doc page in `packages/kerf-chat/llm_docs/`, single LLM
tool, OSS test scenario — at tighter scope.

Order is dictated by dependencies:

```
materials database  ──► parallel, anytime
3D mates (Tier 0)   ──► after Phase 3; unblocks motion + tolerance + FEM contact
tolerance stack-up  ──► after mates
CAM toolpaths       ──► after Phase 2; can parallel mates
topology optim.     ──► after FEM (FEM in a loop)
```

### Materials database

Cross-cutting: FEM (mech + thermal), tolerance (thermal expansion),
drawings (material callouts), Library Parts (default material), and
the architecture project type (building materials) all need a single
source of truth.

- **File kind:** `.material` files inside Library projects, same
  visibility / verified-publisher pattern as `.part`.
- **Properties (v1):** E, ν, ρ, α, yield, ultimate, k, cₚ. Optional:
  S-N curves, stress-strain curves.
- **Seed dataset:** ~500 common engineering materials (steels,
  aluminums, titaniums, copper, plastics, woods, plus building
  materials: concrete, brick, timber, glass, insulation) shipped as
  `kerf-system/materials` with the verified-publisher badge.
- **API:** `kerf.materials.find({...})` returns a reference consumable
  by FEM, Part defaults, tolerance studies, architecture walls/slabs.
- **Phasing:** Mat1 (`.material` kind + seed + FEM consumes). Mat2
  (Parts get default-material field; BOM gains material column). Mat3
  (distributor stock grades).

### 3D assembly mates (Tier 0)

The single biggest unblock — required for motion sim, FEM contact,
tolerance stack-up.

- **Mate types (v1):** coincident, concentric, parallel,
  perpendicular, distance, angle, tangent — between faces, edges,
  vertices, axes.
- **Solver:** investigate planegcs's 3D mode first; fallback is
  **SolveSpace's solver** (GPL3, subprocess only) — most
  production-grade open option.
- **Storage:** new `mates: [...]` array on `.assembly` files; refs use
  Component-relative face IDs.
- **LLM tool:** `add_mate({ type, refs[], value? })`.
- **Phasing:** M1 (basic mates + headless solver). M2 (drag-to-solve +
  conflict highlighting). M3 (motion-study mode: parameterize a mate,
  sweep, animate).
- **Dependencies:** Phase 3 face selection.

### Tolerance stack-up

The analysis layer on top of GD&T frames (already shipped on drawings).

- **Inputs:** two faces (from-face → to-face); the dimension graph
  walks the assembly via mates to find the chain.
- **Methods (v1):** worst-case (sum) and RSS (root-sum-square).
- **Phasing:** T1 (1D worst-case + RSS, min/max distance report). T2
  (Monte-Carlo for non-Gaussian distributions). T3 (3D tolerance
  allocation).
- **LLM tool:** `tolerance_stack({ from_face, to_face, method })`.
- **Dependencies:** 3D mates.

### CAM toolpath generation

Closes the design-to-manufacture loop — next "real engineering output"
pillar after FEM.

- **Library:** **OpenCAMlib** (LGPL 2.1) — used by FreeCAD Path; mature.
  Subprocess on backend; consider WASM in-browser later (~5 MB gz).
- **Operations (v1):** face mill, contour, pocket, drill, profile.
  2.5D only.
- **Output:** G-code with selectable post-processor (LinuxCNC, GRBL,
  Mach3, Fanuc). Toolpath polylines render in the 3D viewport.
- **File kind:** `.cam` — JSON job spec referencing a `.feature`
  source; operation stack same shape as FEM's load-case stack.
- **LLM tool:** `cam_run({ source_file, operations[], post_processor })`.
- **Phasing:** CAM1 (2.5D ops + viewport preview + G-code). CAM2 (3D
  parallel + waterline). CAM3 (lathe + 5-axis). CAM4 (cycle-time +
  collision via CAMotics).
- **Dependencies:** Phase 2 `.feature`.

### Topology optimization

"Make this bracket 30% lighter." Killer chat-driven demo once FEM is in.

- **Solver:** **FEniCSx with UFL-differentiable density-field SIMP** is the v1
  pick — same binary already invoked for FEM. Alternative: **ToOptix**
  (GPL3) for level-set methods.
- **Output:** density field on the mesh → marching-cubes to a new
  mesh. Feature-tree reconstruction is hard; punt to a manual remodel.
- **File kind:** `.topo` — references a `.feature`, defines design
  space + fixed regions; load cases reuse FEM's `fixtures` / `loads`
  vocabulary; adds volume-fraction target.
- **LLM tool:** `topo_run({...})` → optimized mesh + summary metrics.
- **Phasing:** O1 (FEniCSx UFL-SIMP via `pyworker` `/run-topo` + density viz; gradients come for free from UFL — no separate optimization wrapper needed). O2 (mesh
  export). O3 (multi-load-case + manufacturing constraints, e.g.
  3D-print overhang).
- **Dependencies:** FEM landed.

---

## Multi-domain support: project types

A `project_type` enum on the project row is the natural seam for taking
Kerf beyond mechanical CAD into adjacent domains. The chat/files/revisions
plumbing stays shared; the **type gates** which renderer loads, which LLM
tools are exposed, and which file extensions are valid in that project.

### Initial types

| Type | Modeling kernels | Native file kinds | LLM tool surface | Renderer |
|---|---|---|---|---|
| **mechanical** *(today's default)* | JSCAD + (Phase 2) OCCT + (post-P3) FEniCSx | `jscad`, `sketch`, `assembly`, `drawing`, `step`, `feature`, `fem` | feature/sketch/assembly/drawing/fem tools | Three.js 3D + 2D drawing canvas |
| **electronics** | [tscircuit](https://tscircuit.com) (TSX → Circuit JSON) | `circuit.tsx`, `circuit.json`, `netlist` | place-component, connect, set-outline, run-DRC, compile | tscircuit schematic + PCB + 3D-board viewers |
| **architecture** | text-DSL → IFC (IfcOpenShell, LGPL) | `bim`, `ifc`, `drawing`, `sketch`, `material` | wall/slab/opening/space/level ops, IFC compile, BOQ | 2D floor-plan + 3D building view (web-ifc + Three.js) |

Each type ships a sub-package under `src/projectTypes/<name>/` that contributes:
- A renderer component
- A file-tree create menu
- A toolset of LLM tools (registered at boot)
- A set of valid file kinds (validated by handlers)

The LLM system prompt has a per-type addendum so the model knows what tools
it has and the conventions for that domain.

### Migration path
- Add `project_type text not null` to `projects`. Backfill all existing rows to `mechanical` in the same migration; afterwards the column has no default — every new project must declare its type.
- "Create project" requires picking a type up front (no implicit fallback). The picker is the first step of project creation, before naming.
- Workshop is **multi-type from day one**: a single shared gallery surface, with `type` as a filter chip and a per-type result thumbnail (3D render for mechanical, board preview for electronics, floor plan for architecture). Forking preserves the source project's type. Search index, like/fork counts, and insert-from-workshop dialogs all gain a `type` filter and respect type compatibility (e.g., you can only insert an electronics workshop project as a part inside a mechanical project — see cross-domain link below).

### What this is NOT
- It is **not** a way to magically import KiCad or Revit files (those are
  separate import projects under each type).
- It is **not** a runtime-pluggable extension system. Types are built into
  the binary; adding a new one is a code contribution, not a plugin.

---

## Electronics: tscircuit integration (planned)

The first non-mechanical type. Picked because tscircuit's "TSX components
→ Circuit JSON" model maps almost 1:1 onto how Kerf already drives
`.jscad`: the LLM edits a text file, a worker compiles it to a viewable
artifact, file revisions give us undo. Same chat-loop, same diff
semantics, same revisions panel.

### Stack

- **`@tscircuit/core`** — TSX → Circuit JSON compiler.
- **`@tscircuit/pcb-viewer`** + **`@tscircuit/schematic-viewer`** — in-browser 2D renders.
- **`@tscircuit/3d-viewer`** — assembled-board GLTF (board + component bodies).
- **Circuit JSON** — durable intermediate, stored alongside the TSX so
  views can render without re-bundling user code on every load.

### File kinds (electronics project)

```
.circuit.tsx   tscircuit source                 (LLM edits this; the chat-loop target)
.circuit.json  compiled Circuit JSON            (server-rendered cache, derived)
.netlist       SPICE netlist for simulation     (later phase)
.symbol        custom symbol/footprint          (later phase)
```

The TSX is the source of truth; the JSON is a derived artifact, but it
*is* persisted (and revisioned alongside the source) so we can render
schematic / PCB / 3D without running an in-browser bundler on read.

### LLM tool surface (electronics-only registry)

- `place_component({ type, value, refdes?, at? })`
- `connect({ from: "R1.pin1", to: "C1.pin2" })`
- `set_board_outline({ shape: "rect" | "custom", w?, h?, sketch_file? })` — accepts a `.sketch` reference for irregular outlines
- `run_drc()` → list of design-rule violations
- `compile()` → re-derive `.circuit.json` + 3D GLTF + outline SVG

### Renderer (Editor route, dispatched on `project_type`)

- Tabbed schematic / PCB / 3D-board surfaces, replacing the JSCAD viewport.
- Chat panel, file tree, revisions panel, assembly insert dialog — all
  kernel-agnostic and reused unchanged.

---

## Architecture: IFC + text-DSL (planned)

The architectural project type, and the path to "Revit-level over
time" done right for the LLM era. Revit's moat is the BIM data model,
not the UI; **IFC** (Industry Foundation Classes) is the open
equivalent the entire AEC industry has settled on. We use IFC as the
canonical data model and ship a higher-level text-DSL on top — the
LLM edits DSL, a compiler emits IFC, the renderer reads IFC.

### Stack

- **Canonical model: IFC 4.x** (ISO 16739). STEP-based, text-encodable,
  spec public. We implement a subset; same trajectory Revit followed
  for two decades.
- **Library: IfcOpenShell** (LGPL 2.1) — mature C++/Python reader /
  writer / query engine. Subprocess on backend; LGPL is dynamic-link
  clean even bundled. Same license posture as gmsh / ccx.
- **Browser viewer: web-ifc** (Apache 2.0) + **IFC.js / @thatopen** —
  WASM IFC parser + Three.js viewer. MIT/Apache; embeddable.
- **Bonsai (formerly BlenderBIM)** — reference open implementation
  of an IFC-native authoring tool. Studied; not a runtime dependency.

### Source of truth: text-DSL → IFC

The user-facing file is a declarative DSL — readable, diffable,
LLM-tractable. The compiler maps DSL constructs to IFC entities and
persists both. Same pattern as JSCAD → mesh and tscircuit → Circuit
JSON: text source, derived artifact, both revisioned.

DSL example (illustrative; final surface TBD during A1 spike):

```
building "house" {
  site { lat: -33.918, lon: 18.423, orientation: 270deg }

  level "ground" elevation: 0 {
    wall w1 from (0,0)  to (10,0) height: 3.0 thickness: 0.2 type: "brick"
    wall w2 from (10,0) to (10,8) height: 3.0 thickness: 0.2 type: "brick"
    wall w3 from (10,8) to (0,8)  height: 3.0 thickness: 0.2 type: "brick"
    wall w4 from (0,8)  to (0,0)  height: 3.0 thickness: 0.2 type: "brick"

    slab    floor bounds: [w1, w2, w3, w4] thickness: 0.15 type: "concrete"
    space   "living-room" bounds: [w1, w2, w3, w4]

    door    in: w1 at: 2.0 width: 0.9 height: 2.1
    window  in: w2 at: 4.0 width: 1.2 height: 1.5 sill: 0.9
  }

  level "first" elevation: 3.0 { ... }

  roof gable pitch: 30deg eaves: 0.6 covers: ["ground", "first"]
}
```

### File kinds (architecture project)

```
.bim       text-DSL source        (LLM edits this; chat-loop target)
.ifc       compiled IFC bytes     (derived, persisted, revisioned,
                                   exportable to Revit / ArchiCAD)
.drawing   architectural drawings (floor plans, sections, elevations —
                                   reuses existing drawing infra)
.sketch    irregular outlines     (site plans, complex space boundaries —
                                   reuses existing sketcher)
.material  building materials     (shared with mechanical materials database)
```

### Renderer

- **Floor-plan 2D** — top-down clean line drawing per level. Section
  cuts. Annotation. Reuses the existing `.drawing` infra.
- **3D building view** — Three.js + web-ifc/IFC.js. Walk-through
  camera controls. Layer toggles per level / per discipline
  (architecture / structure / MEP).
- **Section views** — vertical or horizontal cut planes with hatched
  cut surfaces.

### LLM tool surface (architecture-only registry)

- `add_wall({ from, to, height, thickness, type })`
- `add_slab({ bounds, thickness, type })`
- `add_opening({ in: wall_id, kind: "door"|"window", at, width, height, sill? })`
- `add_space({ name, bounds })`
- `add_level({ name, elevation })`
- `set_site({ lat, lon, orientation })`
- `compile_ifc()` — re-derive `.ifc` from `.bim`
- `quantity_takeoff()` — BOQ (areas, volumes, material counts)
- `export_ifc()` — IFC file ready for Revit / ArchiCAD round-trip

The model can also `edit_file` the `.bim` text directly; recompile is
automatic on save (same pattern as JSCAD).

### Phasing

- **A1.** "House primitives" minimum: project_type=architecture,
  `.bim` DSL parser, IfcOpenShell-backed compiler, basic entities
  (wall, slab, opening, space, level, site), 2D floor-plan render,
  3D viewer via web-ifc.
- **A2.** Doors/windows as parametric openings with hardware
  (hinges/handles); furniture catalog from Library; section views
  in drawings.
- **A3.** Roofs (gable, hip, flat), staircases, railings.
- **A4.** Multi-building site plans; terrain integration; topo from
  GeoJSON.
- **A5.** MEP runs — basic ductwork, plumbing, electrical conduits +
  fixtures (lights, outlets, panels) via IFC4 MEP entities.
- **A6.** Quantity takeoff (BOQ) — areas per material / per space,
  cost rollup; CSV export.
- **A7.** IFC import — round-trip Revit / ArchiCAD models into the
  kerf model.
- **A8.** Rebar / structural reinforcement (IFC structural domain).
- **A9.** Clash detection between disciplines (architecture vs MEP
  vs structural). Punt to standalone tooling at first; integrate later.

### Cross-domain links

- **`materials` Library** is shared between mechanical and architecture
  — same `.material` kind, same verified publishers, same database.
  An aluminum casting alloy and structural concrete coexist.
- **`drawings`** are kernel-agnostic; floor plans and architectural
  sections reuse the dimension / annotation / sheet infrastructure
  already shipped for mechanical.
- **`sketch`** outlines drive irregular spaces and site boundaries.

### Non-goals (architecture)

- **Full Revit parity v1.** Implementing the IFC subset that covers
  80% of real architectural design takes years; that's exactly what
  Autodesk + ArchiCAD have done. We ship a useful slice early and
  expand iteratively.
- **CFD / HVAC simulation.** Different solver, different culture; far
  future.
- **Structural FEA.** The mechanical FEM stack will not directly
  apply — buildings need beam / shell / plate elements, not solid
  mech. Possibly later via Code_Aster or a building-FEA-specific path.
- **Real-time collaborative editing.** Same posture as the rest of
  the product; deferred indefinitely.
- **Cost estimation beyond quantity takeoff.** Costing is a regional
  / contractor / supplier problem; we expose quantities and let users
  bring their own pricing.

---

## Cross-domain link: PCB-as-part in a mechanical assembly

The single feature that justifies one Kerf binary over two sibling
tools: a mechanical project can reference a PCB from an electronics
project as a positioned part, so the enclosure designer is always
working against the live board outline and the assembled component
heights.

### Data-model extension (assembly Component rows)

Today a Component points at a file inside the same project. We extend
the source descriptor to allow other projects:

```
component {
  id, parent_assembly_id, transform (mat4),
  source: {
    kind: "file"             // existing — same-project file reference
        | "external_project" // new — cross-project artifact reference
    project_id?    // for external_project
    file_id?
    revision_id?   // null = "track latest"; set = pinned to that revision
    artifact:      // which facet of the source we're consuming
      "board_3d"          // assembled board GLTF
      | "board_outline_2d"  // board edge as a sketch profile
      | "model_3d"          // (future) any 3D model exposed by the source project
  }
}
```

Two artifacts a mechanical project can consume from an electronics one:

1. **`board_3d`** — assembled-board GLTF. Inserts as a regular Component:
   gets transforms, clearance checks, collision against enclosure walls.
2. **`board_outline_2d`** — board edge polyline as a sketch profile.
   Useful for designing an enclosure cutout, screw-pattern, or
   mounting-plate footprint from the same source-of-truth.

### Build pipeline (server-side, on electronics-project save)

- TSX → Circuit JSON → cached as a `.circuit.json` revision.
- Circuit JSON → GLTF (headless `@tscircuit/3d-viewer`) → cached as a
  derived artifact keyed by the electronics revision ID.
- Circuit JSON → board outline SVG/Geom2 → cached the same way.

Derived artifacts live in a `derived_artifacts` table (or as a
soft-deleted file kind in the electronics project — TBD) keyed by
`(source_revision_id, artifact_kind)`. They're regenerated lazily on
first request and cached forever; they get garbage-collected when the
source revision is purged.

### Reference resolution (mechanical render path)

- **Pinned** (`revision_id` set): fetch the cached artifact for that
  exact revision. Stable; assembly never changes unless the user
  re-pins.
- **Tracking** (`revision_id` null): fetch the artifact for the
  source's HEAD revision. The Component is flagged "out of date" in
  the assembly tree when the source advances; user can re-accept (which
  pins to the new HEAD) or pin back to a known revision.

### UX

- **Insert-part dialog** gains a "From another project" tab next to the
  existing "From this project" / "From workshop" tabs. Picker chooses
  source project → file → artifact, plus a transform.
- **Workshop insert** also surfaces electronics projects when the
  current edit context is a mechanical assembly, filtered to projects
  that publish a `board_3d` or `board_outline_2d` artifact.
- Referenced PCBs render with a subtle visual treatment (green tint /
  boundary box) so they're distinguishable from in-project geometry.
  Clicking opens the source electronics project in a new tab.

### Phasing

1. **e1.** `project_type` column + UI route dispatch + create-project picker. No electronics editor yet — just the seam, with workshop type-filter wired up so the substrate is in place.
2. **e2.** Electronics project type with tscircuit editor, schematic/PCB viewers, basic LLM tools. No cross-linking. Workshop accepts electronics projects.
3. **e3.** Server-side Circuit JSON + 3D + outline derivation pipeline (cached, revision-keyed).
4. **e4.** Cross-project Component references (electronics → mechanical) with pinned and tracking modes. Insert dialog "From another project" tab.
5. **e5.** Bidirectional hint: mechanical-defined enclosure interior shape feeds back as a board-outline constraint in the source electronics project.

### Non-goals (this phase)
- KiCad/Eagle direct import (separate import-tooling phase; Circuit JSON converters exist upstream).
- Real circuit simulation in the LLM loop (SPICE-via-WASM is a follow-up phase).
- Layout autorouting beyond tscircuit's defaults — punt upstream.

---

## Library / Workshop split

Today `/api/workshop/parts` does double duty — it's both a Workshop sub-tab
("browse public parts") and the only way users discover other people's parts.
That conflates two distinct purposes:

- **Workshop** is project showcase. *"Look what people built, fork it,
  learn from it."* Social, inspirational. Forks an entire project as a new
  starting point.
- **Library** is parts catalog. *"I need an M3 screw / 555 timer /
  NEMA17 stepper to drop into my current assembly right now."* Functional.
  Picked into existing work via a popup, never forked as a project.

### Plan

1. **`/library` top-level route** — parts-focused UI: search, category
   filter, verified-publisher badge, click → details panel with photos
   and distributors. Reuses the existing `/workshop/parts` SQL.
2. **`LibraryPicker` modal** — same data, used by AssemblyEditor's
   *Add component*. Replaces today's project-local dropdown. Searches
   the global Library plus the current project's parts side-by-side.
   Later wired into CircuitEditor's `cad_component` resolution and any
   "place part" tooling in drawings.
3. **Backend: `/api/library/parts`** as the canonical endpoint,
   `/api/workshop/parts` kept as a deprecated alias for one release.
4. **Curation via existing `is_verified_publisher`** — no new tables.
   First-party stock parts (M3×10 screws, etc.) live as a real
   `kerf-system` account's project files; verified-publisher rows
   float to the top of the Library. Same edit/publish flow as any user.
5. **Sharing model mirrors Workshop** — per-Part `visibility='public'`
   field gates inclusion (already present), parent project must not be
   `private` (already enforced). Adding a *Publish to Library* affordance
   on `LibraryEditor` mirrors `PublishButton`'s UX (slug, description,
   thumbnail).

Workshop stays focused on project listings. Library becomes the
discovery surface for individual parts.

---

## BOM rework

`/projects/:id/bom` today is a standalone read-only route divorced from
the model. The intended UX is the opposite:

- **Inline panel inside AssemblyEditor** — collapsible region under the
  component tree, so the BOM updates as you edit and you see the part
  count next to the 3D view.
- **Editing affordances** — quantity overrides (override a rolled-up
  count without restructuring the assembly), non-stocked flags, per-row
  notes. Persisted on the Assembly file, not in a separate table.
- **Distributor data UX** — surface MOQ, lead time, and alternates
  inline. Manual *Refresh prices* button (Library Phase 2 will make this
  automatic).
- The current `/bom` route can stick around as a printable / exportable
  view backed by the same endpoint.

---

## Electronics objects/features fix

CircuitEditor today is a tabbed full-bleed editor (Source / Schematic /
PCB / 3D) — but the editor's left-bottom panel still shows the JSCAD
`ObjectsPanel`, which has nothing to do with circuits. The 3D tab
synthesizes box approximations on the fly from the compiled CircuitJSON.
That's the wrong abstraction.

- **Circuit-specific panel** — replace `ObjectsPanel` for `kind='circuit'`
  files with a Components/Nets list parsed from the compiled CircuitJSON
  (refdes, value, footprint). Updates as the source compiles.
- **Resolve `cad_component` via Library** — when a circuit references
  `cad_component={fileId}`, the 3D tab pulls the actual Library Part's
  geometry instead of rendering a box. Closes the loop with the
  Library-picker work above.
- **Bidirectional link** — picking a part in the Components list
  highlights it on the schematic + PCB + 3D simultaneously
  (cross-view selection sync, mirroring how the mechanical
  ObjectsPanel ↔ Renderer already work).

---

## Electronics: SPICE simulation

Adds simulation as a first-class tab in the CircuitEditor, with results
that visually overlay the existing schematic. Three-phase ramp:

### Phase 1 — Transient + DC analysis (server-side via pyworker)

- **Engine.** [ngspice](http://ngspice.sourceforge.net/) running as a subprocess
  inside the `pyworker` compute sidecar (FastAPI on `:8090`). The
  `POST /run-spice` route accepts a netlist + analysis spec, invokes
  `ngspice -b`, parses the raw output, returns waveforms. Client-side
  WebAssembly path evaluated and dropped — no maintained upstream npm
  package (`ngspice-wasm`, `eda-toolkit/wasm-spice`, etc. all 404 as of
  2026-05-14). pyworker is OSS, brew/pip installable, and already hosts
  FEM/RF/CAM/tess for the same users, so the ops-cost argument that
  drove the sidecar holds for SPICE too.
- **Netlist emit.** A new `src/lib/circuitToSpice.js` walks the compiled
  CircuitJSON and emits a `.cir` netlist:
  - `source_resistor` → `R<refdes> n+ n- <ohms>`
  - `source_capacitor` → `C<refdes> n+ n- <farads>`
  - `source_inductor` → `L<refdes> n+ n- <henries>`
  - `source_voltage_source` → `V<refdes> n+ n- DC <v>` or `SIN(...)` / `PULSE(...)` from a typed `waveform` prop on the tscircuit element.
  - Active devices reference SPICE model cards (BJT, MOSFET, diode) bundled in `kerf-system/spice-models` Library workspace; the Library Part's `spice_model` field overrides for custom MPNs.
- **Probes.** A new schematic tool: click a net or pin to drop a probe.
  Probe markers serialize into the circuit file's `library_mappings`
  comment block (or a sibling `simulation` field). Each probe becomes a
  `.print` / `.save` directive in the netlist.
- **Run.** A new "Simulation" tab next to PCB / 3D in CircuitEditor. UI:
  analysis selector (transient / DC / DC sweep), time / V controls,
  Run button. Results render as a Plotly-style time-series chart (one
  trace per probe). Cursor over the chart highlights the corresponding
  probe on the schematic — that's the user's "link to drawing when
  clicked" metaphor extended to electronics.
- **Storage.** Sim runs persist as `.simulation` files (new `kind`)
  alongside the `.circuit.tsx`. Each `.simulation` references a circuit
  file and stores the analysis spec + last result waveforms (compressed).
  Re-runs don't blow away history — the LLM and the user can compare
  runs over time.

### Phase 2 — AC / Bode / noise + small-signal

- AC sweep: frequency-domain magnitude/phase per probe, log/lin axis.
- Bode plot view (gain + phase vs freq) for op-amp / filter circuits.
- Noise analysis: input-referred noise spectral density.

### Phase 3 — Mixed-signal + behavioural

- Verilog-A / behavioural model support (ngspice has `bsource`).
- Mixed-mode digital + analog co-simulation via Icarus Verilog
  cosimulation hook.

### LLM integration

`run_simulation(circuit_file_id, analysis: 'transient'|'dc'|'ac', ...)`
becomes a tool the model can call. Probe placement remains a user UX
action (the model can recommend probes via comments in the TSX).

### Out of scope (phase 1)

- RF / s-parameters — separate roadmap entry.
- Thermal coupling — distinct domain.
- Schematic-driven simulation directives (FreeCAD-style `.tran` blocks
  inside the schematic) — defer until basic flow ships.

---

## Electronics: RF simulation

Distinct from SPICE because typical SPICE is unreliable above
~100 MHz (parasitic models break down, transmission-line effects
dominate). RF needs a different toolchain.

### Phase 1 — Lumped-network s-parameter analysis

- Library: use [scikit-rf](https://scikit-rf.readthedocs.io/) directly
  via the user's Python (per the Scripting section — Kerf scripts run
  Python on the user's machine via `kerf-sdk`). A `kerf.rf.*` namespace
  in the SDK wraps the common scikit-rf operations (Network, ABCD/S/Z
  conversion, cascade, port renormalization) and writes results into
  the project as a new `.rf-study` file kind. No TS port needed.
- UX: drop matching networks (L-net / Pi-net / T-net) onto a circuit;
  enter source/load impedances; see Smith chart with marker sweep, plus
  S11 / S21 magnitude curves.
- Touchstone (`.s2p`, `.s3p`) import for vendor-supplied parts.

### Phase 2 — Distributed / EM solver

- Integrate [openEMS](https://www.openems.de/) (FDTD method, GPL3).
  Backend subprocess, computational. Project type stays `electronics`,
  but a new `.emsim` file kind references board geometry +
  port definitions and produces field data.
- Antenna / matching-stub design workflow.

### Phase 3 — IBIS / S-parameter signal integrity

- IBIS model loader. Eye-diagram / jitter analysis on differential pairs.
- Useful for high-speed digital — DDR3+, USB, PCIe routing checks.

Multi-quarter; gated on real RF user demand.

---

## Electronics: autorouting

The tscircuit autolayout already handles trace routing for simple
boards. For multi-layer boards with constraints, integrate a real
autorouter:

### Phase 1 — FreeRouting integration

- [FreeRouting](https://github.com/freerouting/freerouting) is the
  open-source autorouter KiCad ships hooks for. Java; GPL3.
- Backend subprocess on save: export tscircuit board to Specctra DSN,
  invoke FreeRouting CLI, import resulting SES, write traces back into
  the CircuitJSON.
- Per-net constraints (width, clearance, layer affinity, length-match)
  surface as TSX props on `<trace>` elements; the exporter encodes them
  in DSN.
- UX: "Auto-route board" button in the PCB tab. Progress + result
  preview before the route is committed.

### Phase 2 — Incremental / push-and-shove routing

- KiCad's interactive router is also available standalone (under
  `pcbnew_router`) but extracting just the routing engine is non-trivial.
  Watch the upstream `freerouting/freerouting` v2 work — they're
  improving interactive UX.

### Phase 3 — ML-assisted reroute

- Watch [DeepPCB](https://www.deeppcb.ai/) and academic ML routers.
  Likely a paid backend service rather than an open-source dependency.
  Punt unless users specifically ask.

---

## Schematic + PCB editor depth

Auto-routing covers fast bring-up; serious electronics work needs manual
control and a real layer stack. This section plans the work to bring the
schematic and PCB editors to KiCad-feature-comparable while keeping every
op LLM-authorable through CircuitJSON edits.

### Phase 1 — Manual trace routing

The user can route by hand: click to start at a pad / net, click to drop
vertices, double-click / Enter to finish. Routing modes:

- **Orthogonal** (90° only) — default, matches most PCB drafting.
- **45° preferred** — orthogonal with 45° corner segments.
- **Free** — any angle (RF / odd geometries).

Operations:
- Drag an existing segment to nudge; endpoints stay locked to vertices.
- Insert a mid-point on hover (click a segment → split).
- T-junction support (3-way connection at a vertex).
- Drag a vertex through another trace → auto-merge nets if same net,
  refuse if different net + show DRC warning.
- Hover a pad → highlight all traces on that net.

Data model in `.circuit.tsx`: append to the existing `traces` array.
Each trace has `points: [{x, y, layer}]` and `net_id`. Already partly
shipped via `appendTrace`.

LLM tools: `route_trace_segments`, `delete_trace`, `split_trace`,
`merge_traces`, `move_trace_vertex`.

Frontend: a `RouteTool` state in `PCBView.jsx` with the click handlers,
preview line, and the "press Esc to cancel / Enter to finish" UX.

### Phase 2 — Copper pours / ground planes

KiCad calls these "filled zones." A pour is a polygon region on a copper
layer connected to a chosen net (typically GND). The pour fills the
polygon minus clearance around traces and pads not on that net. Pads on
the net get thermal-relief spokes.

Data model:
```jsonc
{ "type": "copper_pour",
  "polygon": [{x, y}, ...],
  "layer": "top_copper" | "bottom_copper" | "inner_1" | ...,
  "net_id": "GND",
  "clearance_mm": 0.25,
  "thermal_relief": { "gap": 0.25, "spoke_width": 0.5, "spoke_count": 4 },
  "min_thickness_mm": 0.2,
  "priority": 0
}
```

Rebuild on:
- Net membership change.
- Trace add / move / delete in the polygon.
- Pad add / move / delete.
- Clearance rule change.

Backend: a `compute_pour_fill(pour, board_state)` function in
`packages/kerf-electronics/src/kerf_electronics/routes.py` (pour endpoint) that returns the filled polygon (polygon-with-
holes) as JSON. Uses [shapely](https://shapely.readthedocs.io/) for the
polygon ops + thermal spoke generation.

Frontend: a `PourTool` in `PCBView.jsx` — click vertices → close polygon
→ select net + layer → render fill (transparent at design time, opaque
on export).

LLM tools: `add_copper_pour`, `delete_copper_pour`, `set_pour_net`.

### Phase 3 — Full layer stack (KiCad-equivalent)

Replace the current minimal layer model with a configurable layer stack
mirroring KiCad's. Default 2-layer board; user can switch to 4 / 6 / 8 /
... layers.

Layer types (per IPC-2581 / ODB++ standard):

| Group | Layers (per side or count) |
|---|---|
| Copper | `top_copper`, `inner_1` … `inner_30`, `bottom_copper` |
| Silkscreen | `top_silk`, `bottom_silk` |
| Soldermask | `top_mask`, `bottom_mask` |
| Solder paste | `top_paste`, `bottom_paste` |
| Drill | `drill_plated`, `drill_nonplated` |
| Mechanical | `edge_cuts`, `courtyard`, `fab_notes` |

Data model: `board.layer_stack` array, each entry `{name, type, color,
visible, sublayer_order}`. Components / traces / pours / vias reference a
layer by name.

Frontend: a `LayersPanel` (collapsible right-rail or popout) with:
- Visibility toggle (eye icon).
- Color swatch (click to pick).
- "Solo" mode (Alt-click eye → only this layer visible).
- Drag to reorder.
- "Layer stack preview" — 3D-isometric exploded view showing the physical
  layer stack with thicknesses (FR4 dielectric between copper, etc.).

LLM tools: `add_pcb_layer`, `set_layer_visibility`, `set_layer_color`,
`reorder_layers`, `assign_to_layer`.

### Phase 4 — UX polish

- **Alignment guides**: dragging a component shows dashed alignment
  lines to other components' centers / edges. Same as Figma / Sketch.
- **Snap improvements**: snap to pad center, trace endpoint, trace
  midpoint, grid intersection, layer-edge. Per-snap toggle in toolbar.
- **Theming**: dark / light / oscilloscope (high-contrast) presets;
  per-layer color overrides persist in user preferences.
- **DRC overlay**: design rule check results as colored highlights
  (red = error, amber = warning), click to jump to violation.
- **Multi-select**: marquee select, Shift-click add, Ctrl-click toggle.
- **Undo / redo**: extend the existing file-revisions history to the
  per-edit grain for in-session ops; full-file revisions remain the
  durable layer.
- **Paste from clipboard**: copy selection → JSON to clipboard; paste
  reconstitutes at cursor.

### Phase 5 — DRC + manufacturing output

- **DRC rules engine**: trace width minimum, via clearance, drill spacing,
  silk-on-pad, copper-to-edge. Configurable per-design.
- **Manufacturing export**: Gerber RS-274X (top/bottom/inner copper +
  silk + mask + paste + drill), drill file (Excellon), pick-and-place
  CSV, BOM CSV. `pyworker` `POST /export-gerber` using
  [pcb-tools](https://pypi.org/project/pcb-tools/) or KiCad's command-line
  via subprocess.
- **3D board preview** improvements: render the actual layer stack with
  correct dielectric thicknesses, soldermask transparency, silk overlay.
  Reuses existing 3D viewer.

### LLM-friendliness commitments

- Every routing op is a CircuitJSON edit — the LLM can author a complete
  routed board by emitting JSON.
- Pours are fully declarative (polygon + rules + net); the fill geometry
  is derived, never authored.
- Layer assignments are string refs to a layer-stack registry; the LLM
  reads the stack and references layers by name.
- DRC rules are JSON; the LLM can propose rule changes ("set min trace
  width to 0.15mm") via tool call.

### Priority order

1. **Phase 1** (manual routing) — users want it most; modest scope.
2. **Phase 3** (layer stack) — enables Phase 2 properly; foundational.
3. **Phase 2** (copper pours) — depends on layer stack.
4. **Phase 4** (polish) — quality bar.
5. **Phase 5** (DRC + Gerber) — productionize.

---

## Rhino-parity roadmap

Strategic goal: bring Kerf to feature-equivalent with Rhino 7/8 for the
common workflows (industrial design, jewelry, architectural concept), while
keeping every operation LLM-authorable. The constraint that shapes
everything: **every Rhino feature must round-trip through JSON edited by
either UI tools or LLM tools.** Rhino's GUI commands externalize as nothing;
Kerf's translate as file-kind ops. Most Rhino commands (loft / sweep /
fillet / trim) already fit that shape. The friction is Rhino's free-hand
edits (control-point drag, gumball drag) — for those, the UI emits a delta
op, the file kind stores the op, evaluation produces geometry. Same pattern
as the existing `.feature` system.

### Phase 4a: surface-modeling foundation (~30% shipped)

Already shipped under "Phase 4a: jewelry-priority surfacing":
- `feature_sweep1` / `feature_sweep2` / `feature_network_srf` /
  `feature_blend_srf` LLM tools wired through OCCT.
- Continuity args (C0/C1/C2 for network, G0/G1/G2 for blend).
- Face / edge gumball + Push-Pull / RotateFace / Fillet from selection.

Remaining for Phase 4a:
- **Trim / untrim / split / join / explode / offset** on NURBS surfaces.
- **Polysurface fluency** — multi-face B-rep as one entity, with face
  selection / regroup / explode round-trip.
- **Curve-from-surface** ops: isocurve, edge extraction, intersection
  curves (surface-surface, surface-curve).
- **Surface continuity edges** — G0/G1/G2 tags on shared edges, persist
  through saves, surface-continuity analysis tool.

### Phase 4b: file interop — `.3dm` round-trip

Single highest-impact addition for adoption. Via
[`rhino3dm`](https://github.com/mcneel/rhino3dm) (McNeel, free):

- `pyworker` `POST /import-3dm` — parses a `.3dm` into a tree of
  `.feature` (NURBS BReps), `.sketch` (curves), `.surf` (standalone
  surfaces), `.mesh` (meshes), with layer metadata.
- `pyworker` `POST /export-3dm` — serializes selected files back to a
  `.3dm` for hand-off to Rhino users.
- LLM tool `import_3dm` + file-tree drag-drop hook.
- Maps Rhino's named layers → Kerf's layer hierarchy (Phase 4d).

Marketing demo: drag your `.3dm` library into Kerf and immediately see
the model with the AI chat ready to edit it.

### Phase 4c: SubD modeling

`.subd` file kind, Catmull-Clark via
[OpenSubdiv](https://graphics.pixar.com/opensubdiv/) (Pixar, BSD).
SubD is where Rhino 7+ has been growing — covers industrial design + jewelry.

- Ops: `subdivide`, `smooth_subd`, `crease_edge`, `extrude_face_subd`,
  `bevel_edge_subd`, `extrude_along_face_normal`.
- Conversion: `subd_to_nurbs`, `nurbs_to_subd`, `mesh_to_subd`,
  `subd_to_mesh` (tessellate for display).
- OpenSubdiv subprocess in `pyworker` for fast eval; in-browser
  Catmull-Clark for interactive smoothness preview.

### Phase 4d: layers + display modes

Reusable across all file kinds. `.workspace.json` per-project:

```jsonc
{
  "layers": [
    { "id": "L01", "name": "Geometry", "visible": true, "color": "#ffffff",
      "linetype": "continuous", "material_id": "mat_default" },
    { "id": "L02", "name": "Reference", "visible": true, "color": "#888888",
      "linetype": "dashed" }
  ],
  "display_modes": [
    { "id": "shaded", "wireframe": false, "edges": true },
    { "id": "technical", "wireframe": true, "edges": true, "silhouette": true },
    { "id": "rendered", "shaded": true, "shadows": true }
  ],
  "active_display_mode": "shaded"
}
```

Every file references a `layer_id`. LLM tools: `create_layer`,
`set_layer_visibility`, `assign_to_layer`, `switch_display_mode`.

### Phase 4e: mesh tools

Mesh-domain ops complement NURBS for the import → clean → model bridge.

- `mesh_remesh` (quad), `mesh_decimate`, `mesh_smooth`, `mesh_repair`,
  `mesh_fill_holes`.
- `surface_from_points` (Poisson reconstruction; reverse-engineering
  workflow from scanned data).
- Server-side via [PyMesh](https://pymesh.readthedocs.io/) or
  [OpenMesh](https://www.graphics.rwth-aachen.de/software/openmesh/)
  subprocess in `pyworker`.

### Phase 4f: parametric graph (Grasshopper-equivalent)

**The differentiator.** Rhino's Grasshopper is its moat for parametric
designers. Kerf's `.graph` file kind goes one step further: **the LLM
can author and edit the graph as JSON.** Rhino's Grasshopper has no AI
authoring layer.

- `.graph` JSON: `{nodes: [{id, op, params, inputs: [refs]}],
  outputs: [refs]}`.
- Each `op` resolves to either an existing LLM tool (`feature_sweep2`,
  `sketch_offset`, `material.read`, etc.) or a built-in graph op
  (`number_slider`, `series`, `panel`, `map_each`).
- Re-evaluation on parameter change: traverse DAG, run each node, cache
  intermediate results in `derived_artifacts`.
- Browser-side visual editor via [React Flow](https://reactflow.dev/) —
  drag nodes, connect ports, edit slider values. The editor is a thin
  emitter over the same JSON shape the LLM produces.
- LLM tools: `create_graph_node`, `connect_graph_nodes`,
  `set_graph_param`, `evaluate_graph`.

### Phase 4g: render-quality output

Cloud-tier feature (heavy compute); OSS users run pyworker locally.

- `pyworker` `POST /run-render` invokes Blender (headless) with Cycles.
- `.render` file kind: `{scene: <file_id>, camera, lights[], materials_override,
  resolution, samples, output_format}`.
- Returns PNG / EXR via storage backend; thumbnail-cached.
- LLM tool: `render_scene`.

### Phase 4h: drafting completeness

Extends existing `.drawing` file kind (TechDraw-flavored) toward print-ready:

- Hatch patterns (named patterns from a `.hatch_library`), leader lines,
  rich-text annotations, dimension chains spanning multiple sketches,
  multi-view layouts with bordered crop regions.
- Print preview at sheet size (A0–A4, ANSI A–E), PDF export via the
  existing svg2pdf path.

### Phase 4i: curve depth

Spread across every other phase — added as adjacent features need them:

- `curve_project_to_surface`, `curve_intersect_surface`,
  `curve_from_edge`, `curve_boolean`, `curve_blend`, `curve_match`,
  `curve_offset_3d`, `polyline_to_nurbs`, `curve_simplify`.

### Architectural commitments

These rules apply across all Rhino-parity phases:

- **File-kind = data.** Every Rhino concept becomes a JSON file kind
  with a schema doc in the relevant plugin's `llm_docs/<kind>.md` (most cross-cutting docs in `packages/kerf-chat/llm_docs/`). No exceptions.
- **UI = thin emitter.** Gumballs, drag-handles, control-point editors
  are visual ways to emit the same JSON op the LLM would write.
- **Pyworker = compute.** Heavy NURBS / SubD / mesh ops live in
  `pyworker` as Python; results returned via the same `/run-X` pattern
  as FEM / SPICE / CAM.
- **No black-box GUI state.** If a user can do it, the LLM can do it.
  The reverse must also hold.

### What Kerf has that Rhino doesn't (the moat)

- AI-native — every Rhino op is also an LLM tool.
- Cloud sync + collaboration built in (git-backed).
- Open-source root, MIT.
- Electronics + PCB integration (Rhino doesn't do circuits).
- BOM + distributor pricing.
- Web-native (no install for cloud users).
- Library Parts ↔ Cross-project parts (Rhino's Blocks are simpler).
- Parametric via `.equations` is competitive with Grasshopper for
  scalar-driven design; `.graph` (Phase 4f) closes the visual gap.

If Phase 4a–4f all ship, the positioning is:

> Rhino-level geometry + Revit-level building info (separate IFC track) +
> Grasshopper-level parametric + AI-authoring across all three — in one
> open-source app, with cloud collab built in.

No incumbent has all four.

### Priority order (recommended)

1. **Phase 4a remaining** (trim / untrim / split / join + polysurface) —
   foundation under most Rhino workflows. Already 30% there.
2. **Phase 4b** (`.3dm` round-trip) — single biggest adoption unlock.
3. **Phase 4f** (`.graph`) — the differentiator. The LLM + visual-graph
   combo is uniquely Kerf.
4. **Phase 4c** (SubD) — closes the Rhino 7+ feature gap.
5. **Phase 4d** (layers + display modes) — quality-of-life baseline.
6. **Phase 4e** (mesh tools) — bridge from import to model.
7. **Phase 4h** (drafting completeness) — print-ready output.
8. **Phase 4g** (render) — defer until cloud monetization needs it.
9. **Phase 4i** (curve depth) — ongoing, embedded in other phases.

---

## Performance roadmap (formerly PERFORMANCE.md)

### Phase 1: frontend perf fundamentals — ✅ shipped
- JSCAD eval moved to a Web Worker
- Lazy topology (compute only when measure/drawing tools subscribe)
- File-size-scaled re-eval throttle (250 ms → 3 s for huge files)
- IndexedDB mesh cache keyed by content hash
- Vite manualChunks bundle split (1.6 MB main → 520 KB / 156 KB gzipped)

### Phase 2: reliable STEP uploads — ✅ shipped
- Chunked / resumable upload protocol with SHA-256 integrity
- Polling progress endpoint
- 5 MB chunks, 200 MB cap (configurable)
- Janitor sweeps stale sessions hourly

### Phase 3: server-side STEP pre-tessellation — ✅ shipped

Once Phase 2 stabilizes, browser STEP parsing is the next pain.
**Decision: cloud-tier-only Python sidecar.** OSS local-install
remains browser-only to preserve [[local_install_model]]'s
single-binary install promise.

Options evaluated:
- **A. wazero + occt-import-js WASM** — ❌ infeasible. OCCT WASM is
  compiled against Emscripten's JS host ABI (`__embind_*`, `__emval_*`,
  `_fd_write`), not WASI. Re-implementing embind/emval in wazero is
  weeks of work for marginal gain.
- **B. Node sidecar** — ❌ rejected. Adds a second non-Go runtime to
  the cloud deploy on top of the Python sidecar that CAM/RF/FEM will
  need anyway. One language to operate is strictly better than two.
- **C. CGO bindings to OpenCASCADE** — ❌ deferred. Heaviest build
  chain, biggest binary, cross-compile pain. Not worth the cost when
  the Python sidecar already pays for itself across multiple features.
- **D. Python sidecar via pythonOCC (chosen).** Top-level `pyworker/`
  service exposes `POST /tessellate-step` (and all other heavy-compute
  routes). Existing `step_tessellation_jobs` row + `auto_tess_worker`
  + mesh GLB output all survive — only the sidecar invocation changes
  (HTTP to pyworker instead of subprocess). pythonOCC is the full OCCT binding
  (more capable than the `occt-import-js` import-subset Node package),
  giving headroom for future server-side B-rep work.

**OSS path** stays browser-only by design. Large-STEP OSS users have
an elegant escape hatch: write a `kerf-sdk` script that pre-tessellates
locally via pythonOCC and writes mesh artifacts back into the project
via `kerf.files.write()`. Same Python library either side; the
sidecar pattern is just "where the Python runs."

**Reversibility**: the sidecar boundary itself is the architecture
seam. If a Go-native solution emerges later (CGo, alternative parser,
wazero shim), we swap one Python module without changing the
surrounding plumbing.

After upload finalize: insert a `step_tessellation_jobs` row,
background worker calls the pyworker, produces `.glb`, frontend
prefers the glb to re-parsing the STEP.

### Phase 4: revision DB efficiency — ✅ shipped
- Diff-based revisions: base every N rows + real unified diffs in between (shipped).
- Gzip base and diff payloads as raw `bytea` via `content_codec='gzip'` column (migration `048_revision_compaction.sql`).
- SHA-256 dedup: identical consecutive saves are a no-op at the write layer.
- Safe cap-pruning: never deletes a row that is a `parent_revision_id` for a live diff (chain-integrity protected).
- Canonical `kerf_core.revisions` module replaces 5 copy-pasted `record_revision_for_file` implementations.
- Bug fix: `diff` rows previously stored full gzip-compressed content (not actual diffs); now store unified-diff patches.
- Bug fix: broken `gunzip_bytes` (tried to unpack `r.read()` as tuple) replaced by `_decompress_row` with legacy base64-text fallback.
- 23 hermetic tests in `packages/kerf-core/tests/test_revisions_compaction.py`.

**Phase 5 / future:**
- Background compaction worker: lazily re-compact old chains (worker/cron style).
- Hash-based cross-file dedup: share base content between files with identical sha256 (content-addressable blobs).
- Frontend lazy-preview: revisions panel fetches `content_preview` only; full content loaded on restore (deferred — requires API contract change).

---

## Scalability — large projects + dense scenes

Honest read on the current ceiling. The client renders everything in one
Three.js scene with no LOD, no frustum culling, no draw-call batching;
assemblies are a flat component list (no nesting, no lazy expansion);
heavy CAD compute runs in browser WASM workers (OCCT, JSCAD, tscircuit)
capped at the ~2-4 GB WASM heap.

### Current practical limits

| Scale | Status |
|---|---|
| 100–500 parts | smooth |
| 1k–5k parts | marginal, frame rate drops |
| 10k+ parts (full building, dense PCB) | unresponsive — draw-call bound, not VRAM bound |
| STEP > ~100 MB | may hang the browser on parse |
| Nested assemblies | not supported (must flatten) |

**The bottleneck is draw calls per frame, not GPU memory.** One part =
one draw call. So a building or full-machine assembly chokes long
before VRAM is full. **None of this is architecturally blocked** — the
seams exist (mesh cache, worker boundary, component resolver). It's
unbuilt work.

### Phased plan

Roughly priority-ordered; each phase compounds the previous one. The
first two alone should get us 5-10× the practical part count.

**S1 — Frustum culling (✅ shipped)**

`src/lib/frustumCull.js`: `cullByFrustum(meshes, camera, options)` caches
world-space AABB per mesh (recomputed when `matrixWorld` changes), runs
`Frustum.intersectsBox` per frame, toggles `mesh.visible`. Wired into the
`Renderer.jsx` and `FeatureRenderer.jsx` animation loops. Feature flag:
`localStorage.KERF_FRUSTUM_CULL` (default ON, set to `'0'` to disable).
`setUserVisible(mesh, bool)` lets the hiddenIds toggle coexist with the
per-frame cull without accidental un-hiding. 6 vitest cases in
`src/__tests__/frustumCull.test.js`.

**S2 — Batched draw calls across identical parts (✅ shipped)**

`src/lib/instancingPlan.js`: `planInstances(components)` groups assembly
Components by `(file_id, config_id)`, returns one `InstancedMesh` plan
entry per unique part with ≥ 2 copies (singletons stay as regular Meshes).
Wired into `Renderer.jsx`'s parts-rebuild effect: when `KERF_INSTANCING`
flag is ON and `assemblyComponents` prop is provided, identical parts are
batched into a single `THREE.InstancedMesh` draw call. Picking works:
`raycaster.intersectObject` returns `instanceId` which maps back to
`componentIds[instanceId]` → `Component.id`. `Editor.jsx` derives
`assemblyComponents` (cheap `parseAssembly` call) and passes it to
Renderer. Feature flag: `localStorage.KERF_INSTANCING` (default ON).
7 vitest cases in `src/__tests__/instancingPlan.test.js`.

**S3 — Server-side pre-tessellation (✅ shipped)**

Big STEPs arrive as `.glb` instead of raw B-rep. `AutoTessWorker` in
`packages/kerf-tess/src/kerf_tess/worker.py` wakes on PG NOTIFY, calls
the pyworker `/run-tess` route (pythonOCC), caches the mesh in
`derived_artifacts` keyed by `(file_id, content_sha256, 'step_mesh')`, and
writes `files.mesh_storage_key`. See Performance Phase 3 above.

**S4 — LOD (level of detail)**

Coarse meshes when zoomed out, fine when zoomed in. Mesh decimation
in `pyworker` (pythonOCC + open3d) produces per-part LOD levels
stored as derived artifacts (same cache as STEP pre-tess). Frontend
swaps levels based on screen-space size. **Important once batched
draws are in place** — they amplify each other.

**S5 — Hierarchical assemblies with lazy resolve**

Today's assembly model is a flat component list. Move to a tree:
sub-assemblies as nodes, lazy-expand on demand. Don't tessellate the
whole building to look at one room. Schema change to `.assembly`:
add `subassemblies` array alongside `components`. Frontend
ComponentTree component manages expand/collapse with per-node
visibility + tessellation gating.

This is the bigger architectural lift — affects assembly schema,
BOM rollup (needs to walk tree), git diffs, LLM tool surface.
Probably 4-6 weeks of focused work.

**S6 — IndexedDB-backed mesh streaming**

Today the whole scene's meshes load into VRAM at once. For very
large scenes (10k+ visible parts after culling), stream mesh chunks
from IndexedDB on demand based on view frustum + LOD level. Most
useful AFTER S1+S4 land; before those, this just shifts the bottle-
neck.

### Reversibility seams

The scalability stack is **modular**. Each phase ships behind a
feature flag (`KERF_SCENE_BATCHED`, `KERF_SCENE_LOD`,
`KERF_SCENE_HIERARCHICAL`) so degraded paths stay available if the
new path has bugs. The mesh cache + worker boundary + component
resolver are the architecture seams — all three already exist and
don't need redesign for any phase.

### Non-goals

- **Multi-GPU / distributed rendering.** That's enterprise-vis
  territory; not what a chat-driven CAD tool optimizes for.
- **Game-engine-grade culling** (occlusion + portal culling). S1's
  frustum culling is sufficient for foreseeable CAD scenes; the
  ROI on occlusion culling is poor compared to S2+S4.
- **Real-time multi-million-triangle scenes.** Kerf is for design,
  not for arch-viz walkthroughs. If users need that, they export
  `.glb` and bring it to a viewer optimized for it.

---

## Cloud (hosted-tier) roadmap

The cloud tier is proprietary (see [LICENSE-CLOUD](./LICENSE-CLOUD)). The
public-facing OSS doesn't depend on any of it; everything below `cloud/` is
add-on functionality for the hosted service.

| Capability | Status | Notes |
|---|---|---|
| Paystack billing (USD-priced, ZAR-settled) | ✅ shipped | |
| Workshop (free CAD-design sharing gallery) | ✅ shipped | |
| Project 3D thumbnails (client-side render-on-save) | ✅ shipped | |
| Git (commits + branches + merge + GitHub sync) | ✅ shipped | |
| Multi-lane git graph | ✅ shipped | |
| Stateless object-storage git backend | ✅ shipped | `S3GitStorer` (`packages/kerf-core/src/kerf_core/storage/git_storer.py`) bulk-syncs bare pygit2 repos to/from R2/S3. Objects-before-refs upload order + `_marker` ETag concurrency check + batch orphan delete. Wired into the cloud-only `git_push` / `git_pull` routes in `packages/kerf-cloud/src/kerf_cloud/routes.py` behind an `isinstance(storage, S3Storage)` guard so the OSS filesystem path is unaffected. 6 hermetic moto integration tests in `packages/kerf-core/tests/test_git_storer.py` cover the full round-trip + repack + race detection. Docs: `docs/cloud.md` § S3 Git Storer. |
| `pyworker` service (Python sidecar) | ✅ shipped | Per-plugin FastAPI routes, assembled by the plugin loader. Routes shipped: `/tessellate-step` (`kerf-tess`), `/run-mates` (`kerf-mates`), `/run-cam` (`kerf-cam`), `/run-rf` + `/autoroute-circuit` (`kerf-electronics`), `/run-fem` (`kerf-fem` — **FEniCSx primary; CalculiX as documented second-solver behind same route**), `/run-topo` (`kerf-topo`), `/compile-ifc` + `/compile-bim` (`kerf-bim`), `/import-kicad` + `/import-kicad-library` (`kerf-electronics`), `/import-freecad` (`kerf-imports`), `/run-spice` (`kerf-electronics`), `/import-rhino3dm` (`kerf-imports`), `/render` (`kerf-render`). One Python runtime hosts every heavy-compute server-side feature — amortizes ops cost. Cloud-tier wires it via `packages/kerf-workers/src/kerf_workers/runner.py`; OSS local-install path uses the per-plugin routes directly when installed (otherwise browser-side fallback). Preserves [[local_install_model]]. |
| API tokens (cloud) for `kerf-sdk` auth | ✅ shipped | `api_tokens` table (migration `025_api_tokens.sql`) with `scopes jsonb`, `last_used_at`, soft-revoke; `packages/kerf-core/src/kerf_core/db/queries/api_tokens.py` query layer; `POST/GET/DELETE /api/api-tokens` endpoints in `packages/kerf-auth/src/kerf_auth/routes.py` (workspace context via `?workspace_slug=` query param for JWT-auth callers); `WorkspaceSettings.jsx` API Tokens card with issue/list/revoke flow. Workspace-scoped opaque tokens (`kerf_sk_` + 32 chars, DB-lookup not JWT). Out of scope v1: browser device flow, scope-narrowing UI, full audit log, multi-workspace tokens. |
| Email notifications (account, billing) | ✅ shipped | |

---

## Documentation roadmap

- **README.md** — front door, quickstart, build, links. *Improving.*
- **ROADMAP.md** — this document.
- **`docs/`** — extended guides (planned). Sketching, assemblies, drawings,
  cloud, contributing, architecture deep-dive.
- **Landing page** (`src/routes/Landing.jsx`) — *being revamped.*
- **`backend/README.md`** — backend-specific dev guide.
- **`docs/cloud-operator.md`** — cloud-tier build/deploy.

---

## Imports from external CAD/EDA tools

Adoption multiplier. Most engineers arrive at Kerf with existing
investment in **KiCad / FreeCAD / OpenSCAD** designs. Lossless
re-import is a strategic mismatch — it would mean re-implementing
each of those tools. The right framing is **first-cut import +
LLM refinement**: the import path produces a working starting point
in a native Kerf file kind; the user iterates from there via chat,
script, or direct edit.

### Shared architectural pattern

All three imports follow one shape:

1. **Parsing happens in `pyworker`** (or browser-side for OpenSCAD,
   where the grammar is small enough). Each ecosystem has a mature
   Python (or JS) parser we plug in — no parsers written from
   scratch.
2. **Output is a native Kerf file kind** the LLM can already work
   with. No new editor surface to maintain; the existing
   `.circuit.tsx` / `.feature` / `.sketch` / `.equations` / `.jscad`
   editors handle the result.
3. **Reversibility seam at the parser boundary** — each import is a
   single `pyworker` route (or browser worker), swappable when better
   parsers emerge.
4. **3D model / binary asset blobs go through `.step-ref`
   pointer-in-storage** (the pattern shipped from the large-file STEP
   row). Importing 200 footprints with STEP models doesn't bloat git.
5. **LLM tools** wrap the import flow so the model can invoke imports
   conversationally: "import this KiCad project and convert the LDO
   to the equivalent in our Library Parts."

### Comparison

| Import | Target file kind | Parser location | Difficulty | Strategic value |
|---|---|---|---|---|
| **KiCad** | `.circuit.tsx` (tscircuit) | `pyworker` | Medium (translation tables) | High — large user base |
| **FreeCAD** | `.feature` + `.sketch` + `.equations` | `pyworker` (FreeCAD Python lib) | Hard (rich data model) | High — direct competitor's users |
| **OpenSCAD** | `.jscad` | Browser-side (small grammar) | Easy (sister CSG language) | Medium — maker / 3D-print community |

### Rollout sequence

Recommended order based on difficulty + signal value:

1. **OpenSCAD Tier 1 first** — easiest, fastest, validates how
   import-driven users behave in Kerf. Browser-side, no `pyworker`
   dependency, ships fastest.
2. **KiCad Tier 1** — already roadmapped as 📋 next; pyworker is
   available via the per-plugin package loader.
3. **FreeCAD Tier 1** — the big strategic prize. FreeCAD users are
   Kerf's most natural target audience: open-source-friendly,
   parametric-CAD-trained, often Python-comfortable.
4. **Tier 2 of each** as adoption signal demands.

---

### KiCad (electronics)

**Status**: 📋 next.

**Tier 1 — schematic + PCB first-cut**

- `pyworker` route `POST /import-kicad-project` accepts a zipped
  KiCad project (or individual `.kicad_sch` / `.kicad_pcb` files).
- Parser: [`kiutils`](https://github.com/mvnmgrx/kiutils) or
  [`kicad-python`](https://github.com/pointhi/kicad-python) — pure
  Python, no KiCad install required on the worker.
- Output: a `.circuit.tsx` file using tscircuit primitives.
  - Common parts (R / C / L / basic ICs by pin count) map cleanly
  - Uncommon parts become `<chip>` with the right pin count + comment
    noting the original KiCad symbol name
- Net translation: each KiCad net → a tscircuit `<trace>` connecting
  the relevant ports.
- Schematic placement → x/y on schematic; PCB placement → x/y + layer
  on PCB.
- Footprint translation: KiCad footprint identifier → tscircuit
  footprint string via a translation table. Ship with ~100 most
  common; unknown footprints get `<chip footprint="kicad:lib:name">`
  placeholder.
- LLM tool: `kicad_import_project(zip_blob | url) → .circuit.tsx path`.

**Tier 2 — libraries + 3D models**

- KiCad symbol library (`.kicad_sym`) → ingest each symbol as a Kerf
  Library Part. Verified-publisher pattern (already shipped) handles
  curation.
- KiCad footprint library (`.pretty/*.kicad_mod`) → ingested into the
  Library Part metadata (footprint string + pad layout).
- KiCad 3D models (STEP / VRML linked from footprints) → ingested as
  `.step-ref` pointers. Blobs in object storage, pointers in git.
  tscircuit's 3D board view resolves them transparently. **This is
  precisely the use case the pointer pattern was built for.**
- LLM tools: `kicad_import_library(zip | dir)`,
  `kicad_match_part(refdes, hint?)` — fuzzy match against existing
  Library Parts with confidence scores.

**Tier 3 — explicitly out of scope**

- Lossless round-trip / export back to KiCad
- 1:1 layout fidelity, differential pairs, layer stack-ups, custom
  design rules
- Hierarchical schematic sheets preserved as nested TSX
- ERC/DRC rule preservation

Building these is "make Kerf into a KiCad-equivalent EDA tool" —
strategic mismatch. Users who need full fidelity stay in KiCad and
export Gerbers from there.

**Honest blockers**

- Footprint translation table needs curation (~100 common shipped,
  long tail goes to placeholder; LLM can suggest mappings on import)
- Symbol library scale: KiCad standard libraries have ~10,000 symbols
  → lazy-import-on-use rather than bulk ingest
- Hierarchical schematics flatten in v1; full nesting is Phase 2 if
  demand emerges

---

### FreeCAD (mechanical)

**Status**: 📋 planned.

**Why this is the big strategic prize**: FreeCAD users are Kerf's
most natural audience — open-source-friendly, parametric-CAD-trained,
often Python-comfortable. They've self-selected against proprietary
CAD; they're already comfortable with command-line / script-driven
workflows.

**Why it's the hardest**: FreeCAD's data model is richer than KiCad's
by an order of magnitude.

**The good news — kernel alignment.** FreeCAD uses OpenCascade,
same as Kerf's `.feature` files. BRep geometry transfers without
re-meshing — both speak the same TopoDS representation. Tier 1 lifts
the BRep state directly.

**Tier 1 — Part + PartDesign features**

- `pyworker` route `POST /import-freecad-project` accepts `.FCStd`
  (ZIP containing XML + binary BRep blobs).
- Parser: official `FreeCAD` Python module (heavyweight install on
  the worker — accept the install cost; alternative `kiutils`-style
  community parsers are less complete).
- Walk the document tree. Map FreeCAD features → Kerf `feature_*`
  ops:
  - `Pad` / `Pocket` / `Revolve` / `Hole` / `Fillet` / `Chamfer`
  - `Shell` / `Sweep` / `Loft` / `Mirror` / `LinearPattern` /
    `PolarPattern`
  - All conceptually 1:1 with Kerf's existing OCCT-backed ops.
- BRep blob preservation via `.step-ref` pattern — extract the OCCT
  TopoDS blobs, store via content-hash, reference. No re-tessellation.
- Output: a `.feature` file with the operation tree + accompanying
  `.sketch` files for sketch-driven features.
- LLM tool: `freecad_import_project(zip_blob | url) → .feature path`.

**Tier 2 — Sketcher + Spreadsheet + Library + TechDraw**

- FreeCAD Sketcher constraints → planegcs equivalents. Most map
  cleanly (parallel, perpendicular, equal, distance, angle, tangent
  — shared vocabulary). Subtle differences in symmetry and
  multi-constraint conjunctions need a translation pass; unmappable
  constraints become read-only construction geometry with a comment.
- FreeCAD Spreadsheet → Kerf `.equations` file. Surprisingly clean
  mapping — both are named-parameter tables. Cell-formula syntax
  translates to mathjs expressions.
- FreeCAD Material library → Kerf Materials Library (already shipped).
  Direct field mapping.
- FreeCAD TechDraw drawings → Kerf `.drawing` file. Lossy on
  dimension styles; coordinate system + projection + dimensions
  themselves carry over.

**Tier 3 — Python macros migration (organic)**

FreeCAD users with Python macros are the **most natural kerf-sdk
audience** — they already write Python that drives CAD. But:

- FreeCAD's Python API (`App`, `FreeCAD.Gui`, `Part.makeBox`, etc.)
  is incompatible with kerf-sdk's API. Auto-translation is brittle.
- Strategy: don't auto-translate. Provide an LLM tool
  `freecad_macro_assist(file) → markdown explanation + suggested
  kerf-sdk equivalent` that:
  1. Explains what the FreeCAD macro does
  2. Drafts an equivalent kerf-sdk script
  3. Lets the user iterate in chat to refine
- This is *positioning*, not feature-completeness: "your Python
  knowledge transfers; we don't auto-port your macros."

**Tier 4 — explicitly out of scope**

- FEM workbench data (users move to Kerf FEM)
- Path workbench (users move to Kerf CAM)
- BIM workbench (users move to Kerf Architecture project type)
- Continuous sync / round-trip export back to `.FCStd`
- Workbenches we don't have equivalents for (Surface, Mesh, Robot,
  Ship, etc.) — show "not yet supported" warning on import

**Honest blockers**

- FreeCAD's `.FCStd` is a moving format target. New FreeCAD versions
  occasionally break parsers. Pin a Python module version and update
  on user reports.
- Document graph recompute semantics: FreeCAD features reference each
  other by name; broken references on rename are real. Tier 1 imports
  the resolved-at-export state and ignores the recompute graph (loses
  parametric edits to the imported features). Acceptable for v1.
- Sketcher constraint translation is the hardest single piece. Plan
  for ~2 weeks of careful work on this alone.

---

### OpenSCAD (mechanical / maker)

**Status**: 📋 planned. **No pyworker dependency** — ships
independently of the Python sidecar.

**Why this is the cleanest of the three**: OpenSCAD and JSCAD are
sister CSG languages. Same mental model — primitives, boolean ops,
transforms, modules, functions. The translation is nearly mechanical.

**Tier 1 — direct translation**

- Browser-side parser (the OpenSCAD grammar is small enough; use
  `openscad-parser` npm package or hand-roll a tiny one).
- Source-to-source emitter: `.scad` → `.jscad` JavaScript.
- Direct primitive mapping:
  - `cube`, `sphere`, `cylinder`, `polygon`, `polyhedron`
  - `union`, `difference`, `intersection`
  - `translate`, `rotate`, `scale`, `mirror`, `multmatrix`
  - `linear_extrude`, `rotate_extrude`
- Output: `.jscad` file producing visually identical geometry.
- LLM tool: `openscad_import(scad_source | file) → .jscad path`.

**Tier 2 — full op coverage**

- `hull()` — JSCAD has hull module; direct map
- `minkowski()` — JSCAD has minkowski; slow but functional
- `import("file.stl")` / `surface("file.png")` — translate to JSCAD
  imports; file path translation needed; heightmap surfaces are
  trickier (likely fall through to subprocess escape hatch)
- `text("...")` — JSCAD has text; font handling differs (default
  font substitution + warning)
- Customizer parameter blocks (`/* [Group] */`) → JSCAD parameter
  metadata for the parameter UI

**Tier 3 — modules and functions**

- `module foo(a, b=10) {...}` → JS function with default-arg
  destructuring
- Recursive modules work but need recursion-limit care (OpenSCAD's
  recursion limit is configurable; JSCAD's is the JS engine's stack)
- Functions (`function f(x) = ...`) → JS arrow functions

**Escape hatch — OpenSCAD subprocess**

For `.scad` files that use exotic features (`surface()` heightmaps,
animation directives, custom render hints) or that hit translation
bugs: run OpenSCAD itself as a subprocess (in `pyworker`'s
`/import-openscad-subprocess` route) and import the resulting STL as
a mesh. Loses parametric model. Useful fallback rather than primary
path.

**Tier 4 — explicitly out of scope**

- 1:1 visual fidelity of OpenSCAD's preview renderer (we use JSCAD's
  preview)
- ANIMATE directive / animation export
- Customizer auto-build with parameter sweeps (could be a kerf-sdk
  pattern instead)

**Architectural note**

OpenSCAD's parser is small enough to run in a Web Worker — no
`pyworker` round-trip needed for Tier 1. This is the **only one of
the three imports that doesn't need cloud-tier infrastructure** to be
useful. OSS local install can ship full OpenSCAD import without
running a sidecar. That makes it an attractive "first import to
ship" — fast win, no deploy story changes.

---

### Non-goals (imports as a whole)

- **Continuous sync.** Import is one-shot. KiCad → Kerf, user iterates
  in Kerf, no re-sync back. Users who want bidirectional sync stay in
  their source tool.
- **Workbench-level features that don't map cleanly.** FreeCAD has
  20+ workbenches; only Part / PartDesign / Sketcher map to Kerf's
  `.feature` model in Tier 1. Others either fall through to Kerf
  equivalents (Kerf FEM/CAM/Architecture) or show "not supported"
  warnings.
- **Visual EDA / CAD tooling parity.** Kerf's modeling is LLM-driven
  + script-driven; we're not building visual KiCad / FreeCAD inside
  Kerf. Import gives a starting point; refinement is via chat and
  kerf-sdk.
- **Manufacturer-shipped library mirrors.** We don't bulk-ingest
  KiCad / FreeCAD official libraries upfront — they're available on
  demand via the import tools. Manufacturers who want their parts
  pre-shipped in Kerf go through the verified-publisher Library
  pipeline (already shipped).
- **Format-specific export.** Export from Kerf goes through `.step`
  (mechanical) / Gerbers-via-tscircuit (electronics) / `.ifc`
  (architecture). We don't export back to `.FCStd` / `.kicad_pcb` /
  `.scad`.

---

## How to contribute

- **OSS contributions** are welcome under the MIT license. Pick anything
  marked 📋 or 🔮 in the table above.
- **Cloud contributions** require a separate license agreement; reach out
  before opening PRs against `cloud/` paths.
- **Bug reports**: GitHub Issues.
- **Architecture discussions**: GitHub Discussions when we open one.

The code structure mirrors this roadmap: `packages/` is the OSS Python monorepo (MIT-licensed plugins), `cloud/` is cloud-tier Python (proprietary), `src/` is OSS frontend, `src/cloud/` is cloud frontend. New features land in the right tree based on their license.
