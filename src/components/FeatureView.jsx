// FeatureView — editor for `.feature` files (OCCT B-rep timeline + Phase 3
// direct modeling on top).
//
// Layout:
//   * top      — single unified toolbar: Add-feature popover + file name +
//                feature timeline (chips) on the left; pick-mode controls
//                (Faces / Edges / Push-Pull / Sketch-on-face) on the right.
//   * center   — FeatureRenderer (Phase 3): clickable faces + edges, hover
//                highlight, push/pull drag, sketch-on-face, etc.
//   * right    — FeatureInspector for the selected feature. When the
//                inspector has selection-driven fields (Fillet/Chamfer
//                edges, Shell faces, pattern axes, ...) it shows the current
//                viewport selection and a "Pick in viewport" button that
//                arms a one-shot pick.
//   * bottom   — eval status, vertex/body count, viewport selection summary,
//                error banner, re-evaluate.
//
// Selection lifecycle:
//   - Selection is per-file, session-only (lives in the workspace store at
//     `featureSelection`). On file switch we clear it.
//   - Face/edge ids are NOT stable across structural feature edits — adding
//     or removing features re-runs the OCCT evaluator and edge ids shuffle
//     in TopExp explorer order. We display a yellow banner "Selections may
//     reset after structural changes" to set expectations. A future polish
//     would pin selections to (face_centroid, normal) tuples for soft-
//     persistence.
//
// Push/pull UX:
//   - Toolbar button "Push/Pull" toggles a special pick mode. When armed,
//     hovering a face highlights it amber. Mousedown anchors the drag,
//     mouse-move projects screen delta onto the face's normal direction
//     (SketchUp-style). Release commits — append a `push_pull` feature node
//     to the tree (positive distance → fuse outward, negative → cut inward).
//     The face's id is captured at click time; the worker re-evaluates on
//     commit and the topology re-numbers, so the inspector can't "edit" a
//     completed push/pull (it's stored as a generic node and the user has
//     to re-pick the face if they want to change the distance).
//
// Sketch-on-face UX:
//   - Toolbar button "Sketch on face" arms a one-shot face pick. Click a
//     face → modal asks for a sketch name + parent folder → creates a new
//     sketch file with `plane: {type:'face', file_id, feature_node_id,
//     face_id}`. The sketcher reads this and builds a world-space transform
//     from the OCCT face frame.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Trash2, ChevronUp, ChevronDown, Box, Circle, RotateCcw,
  Disc, Layers, Drill, Sigma, AlertTriangle, Loader2, Play,
  Move, Crosshair, GitBranch, Repeat, FlipHorizontal,
  PencilLine, Pointer, Waves, Layers3, Aperture, Plus,
  X, ChevronRight, LayoutGrid, Combine, Scissors, Grid3x3,
} from 'lucide-react'
import FeatureRenderer from './FeatureRenderer.jsx'
import {
  runFeatures, prewarmOcct, newFeatureId,
  requestFaceOutline,
} from '../lib/occtRunner.js'
import { useWorkspace } from '../store/workspace.js'

// Catalog of feature operations the LLM tools also expose. Each entry
// describes the icon, default param values, and the schema for the right-
// hand parameter inspector.
const FEATURE_KINDS = [
  {
    op: 'pad',
    label: 'Pad',
    icon: Box,
    defaults: { sketch_path: '', height: 10, direction: 'up' },
    fields: [
      { key: 'sketch_path', kind: 'sketch_picker', label: 'Sketch' },
      { key: 'height', kind: 'number', label: 'Height (mm)', min: 0.001 },
      { key: 'direction', kind: 'select', label: 'Direction', options: [
        { value: 'up', label: 'Up (+Z)' },
        { value: 'down', label: 'Down (-Z)' },
        { value: 'symmetric', label: 'Symmetric' },
      ] },
    ],
  },
  {
    op: 'boss_with_draft',
    label: 'Boss + draft',
    icon: Box,
    defaults: {
      sketch_path: '',
      height: 10,
      direction: 'up',
      draft_angle_deg: 3,
      draft_direction: 'outward',
    },
    fields: [
      { key: 'sketch_path', kind: 'sketch_picker', label: 'Sketch' },
      { key: 'height', kind: 'number', label: 'Height (mm)', min: 0.001 },
      { key: 'direction', kind: 'select', label: 'Direction', options: [
        { value: 'up', label: 'Up (+Z)' },
        { value: 'down', label: 'Down (-Z)' },
        { value: 'symmetric', label: 'Symmetric' },
      ] },
      { key: 'draft_angle_deg', kind: 'number', label: 'Draft angle (°)', min: -30, max: 30 },
      { key: 'draft_direction', kind: 'select', label: 'Draft direction', options: [
        { value: 'outward', label: 'Outward (widen away from sketch)' },
        { value: 'inward', label: 'Inward (narrow toward sketch)' },
      ] },
    ],
  },
  {
    op: 'pocket',
    label: 'Pocket',
    icon: Disc,
    defaults: { sketch_path: '', depth: 5, target_id: '' },
    fields: [
      { key: 'sketch_path', kind: 'sketch_picker', label: 'Sketch' },
      { key: 'depth', kind: 'number', label: 'Depth (mm)', min: 0.001 },
      { key: 'target_id', kind: 'feature_picker', label: 'Target body' },
    ],
  },
  {
    op: 'cut_from_sketch',
    label: 'Cut from sketch',
    icon: Disc,
    defaults: { target_id: '', target_face_id: -1, target_face_name: '', sketch_path: '', depth: 5, reverse: false },
    fields: [
      { key: 'target_id', kind: 'feature_picker', label: 'Target body' },
      { key: 'target_face_id', kind: 'face_picker_single', label: 'Face' },
      { key: 'sketch_path', kind: 'sketch_picker', label: 'Sketch' },
      { key: 'depth', kind: 'number', label: 'Depth (mm)', min: 0.001 },
      { key: 'reverse', kind: 'bool', label: 'Reverse direction' },
    ],
  },
  {
    op: 'revolve',
    label: 'Revolve',
    icon: RotateCcw,
    defaults: { sketch_path: '', axis: 'z', angle_deg: 360 },
    fields: [
      { key: 'sketch_path', kind: 'sketch_picker', label: 'Sketch' },
      { key: 'axis', kind: 'select', label: 'Axis', options: [
        { value: 'x', label: 'X' },
        { value: 'y', label: 'Y' },
        { value: 'z', label: 'Z' },
      ] },
      { key: 'angle_deg', kind: 'number', label: 'Angle (deg)', min: 1, max: 360 },
    ],
  },
  {
    op: 'fillet',
    label: 'Fillet',
    icon: Circle,
    defaults: { target_id: '', edge_filter: 'all', radius: 1, edge_ids: [] },
    fields: [
      { key: 'target_id', kind: 'feature_picker', label: 'Target body' },
      { key: 'edge_filter', kind: 'select', label: 'Edges', options: [
        { value: 'all', label: 'All' },
        { value: 'horizontal', label: 'Horizontal' },
        { value: 'vertical', label: 'Vertical' },
        { value: 'manual', label: 'Manual (pick)' },
      ] },
      { key: 'edge_ids', kind: 'edge_picker', label: 'Picked edges',
        showWhen: (n) => n.edge_filter === 'manual' },
      { key: 'radius', kind: 'number', label: 'Radius (mm)', min: 0.001 },
    ],
  },
  {
    op: 'chamfer',
    label: 'Chamfer',
    icon: Sigma,
    defaults: { target_id: '', edge_filter: 'all', distance: 1, edge_ids: [] },
    fields: [
      { key: 'target_id', kind: 'feature_picker', label: 'Target body' },
      { key: 'edge_filter', kind: 'select', label: 'Edges', options: [
        { value: 'all', label: 'All' },
        { value: 'horizontal', label: 'Horizontal' },
        { value: 'vertical', label: 'Vertical' },
        { value: 'manual', label: 'Manual (pick)' },
      ] },
      { key: 'edge_ids', kind: 'edge_picker', label: 'Picked edges',
        showWhen: (n) => n.edge_filter === 'manual' },
      { key: 'distance', kind: 'number', label: 'Distance (mm)', min: 0.001 },
    ],
  },
  {
    op: 'shell',
    label: 'Shell',
    icon: Layers,
    defaults: { target_id: '', thickness: 1, face_ids: [] },
    fields: [
      { key: 'target_id', kind: 'feature_picker', label: 'Target body' },
      { key: 'face_ids', kind: 'face_picker', label: 'Faces to remove' },
      { key: 'thickness', kind: 'number', label: 'Thickness (mm)', min: 0.001 },
    ],
  },
  {
    op: 'hole',
    label: 'Hole',
    icon: Drill,
    defaults: { sketch_path: '', target_id: '', diameter: 3, depth: 5 },
    fields: [
      { key: 'sketch_path', kind: 'sketch_picker', label: 'Center sketch' },
      { key: 'target_id', kind: 'feature_picker', label: 'Target body' },
      { key: 'diameter', kind: 'number', label: 'Diameter (mm)', min: 0.001 },
      { key: 'depth', kind: 'number', label: 'Depth (mm)', min: 0.001 },
    ],
  },
  {
    op: 'hole_pattern',
    label: 'Hole pattern',
    icon: LayoutGrid,
    defaults: { target_id: '', sketch_path: '', diameter: 3, depth: 5 },
    fields: [
      { key: 'sketch_path', kind: 'sketch_picker', label: 'Points sketch' },
      { key: 'target_id', kind: 'feature_picker', label: 'Target body' },
      { key: 'diameter', kind: 'number', label: 'Diameter (mm)', min: 0.001 },
      { key: 'depth', kind: 'number', label: 'Depth (mm)', min: 0.001 },
    ],
  },
  {
    op: 'linear_pattern',
    label: 'Linear pat.',
    icon: Repeat,
    defaults: { direction: 'x', count: 3, spacing: 10 },
    fields: [
      { key: 'direction', kind: 'axis_picker', label: 'Direction (axis or edge)' },
      { key: 'count', kind: 'number', label: 'Count', min: 2, step: 1 },
      { key: 'spacing', kind: 'number', label: 'Spacing (mm)' },
    ],
  },
  {
    op: 'polar_pattern',
    label: 'Polar pat.',
    icon: GitBranch,
    defaults: { axis: 'z', count: 6, total_angle_deg: 360 },
    fields: [
      { key: 'axis', kind: 'axis_picker', label: 'Axis (axis or edge)' },
      { key: 'count', kind: 'number', label: 'Count', min: 2, step: 1 },
      { key: 'total_angle_deg', kind: 'number', label: 'Total angle (deg)', min: 1, max: 360 },
    ],
  },
  {
    op: 'mirror_pattern',
    label: 'Mirror',
    icon: FlipHorizontal,
    // T6: plane_face_name dual-writes the persistent face name alongside the
    // plane field (which can be a numeric face id when picked from the viewport).
    defaults: { plane: 'xy', plane_face_name: '' },
    fields: [
      { key: 'plane', kind: 'plane_picker', label: 'Plane (axis-pair or face)' },
    ],
  },
  {
    op: 'push_pull',
    label: 'Push/Pull',
    icon: Move,
    defaults: { face_id: -1, face_name: '', distance: 0 },
    fields: [
      { key: 'face_id', kind: 'face_picker_single', label: 'Face' },
      { key: 'distance', kind: 'number', label: 'Distance (mm) — negative = into body' },
    ],
  },
  // Phase 4 starter — Rhino-flavored ops. Worker has full implementations;
  // inspector here uses the simplest field kinds. Loft + variable-radius-
  // fillet expose minimal v1 UIs; richer multi-profile reordering and
  // per-vertex-radius editors are follow-up polish.
  {
    op: 'sweep1',
    label: 'Sweep1',
    icon: Waves,
    defaults: { profile_sketch_path: '', path_sketch_path: '', twist_deg: 0, scale_end: 1, mode: 'auto' },
    fields: [
      { key: 'profile_sketch_path', kind: 'sketch_picker', label: 'Profile sketch' },
      { key: 'path_sketch_path', kind: 'sketch_picker', label: 'Path sketch' },
      { key: 'twist_deg', kind: 'number', label: 'Twist (°)', step: 1 },
      { key: 'scale_end', kind: 'number', label: 'End scale', min: 0.001, step: 0.05 },
      { key: 'mode', kind: 'select', label: 'Mode', options: [
        { value: 'auto', label: 'Auto' },
        { value: 'frenet', label: 'Frenet' },
        { value: 'corrected_frenet', label: 'Corrected Frenet' },
      ] },
    ],
  },
  {
    op: 'sweep2',
    label: 'Sweep2',
    icon: Waves,
    defaults: { profile_sketch_path: '', rail1_sketch_path: '', rail2_sketch_path: '', twist_deg: 0, scale_end: 1, mode: 'auto' },
    fields: [
      { key: 'profile_sketch_path', kind: 'sketch_picker', label: 'Profile sketch' },
      { key: 'rail1_sketch_path', kind: 'sketch_picker', label: 'Rail 1 sketch' },
      { key: 'rail2_sketch_path', kind: 'sketch_picker', label: 'Rail 2 sketch' },
      { key: 'twist_deg', kind: 'number', label: 'Twist (°)', step: 1 },
      { key: 'scale_end', kind: 'number', label: 'End scale', min: 0.001, step: 0.05 },
      { key: 'mode', kind: 'select', label: 'Mode', options: [
        { value: 'auto', label: 'Auto' },
        { value: 'frenet', label: 'Frenet' },
      ] },
    ],
  },
  {
    op: 'loft',
    label: 'Loft',
    icon: Layers3,
    defaults: { profile_sketch_paths: [], ruled: false, symmetric: false, closed: false, continuity: 'C0' },
    fields: [
      { key: 'profile_sketch_paths', kind: 'sketch_path_list', label: 'Profile sketches (≥2, ordered)' },
      { key: 'ruled', kind: 'bool', label: 'Ruled (linear blends)' },
      { key: 'symmetric', kind: 'bool', label: 'Symmetric (mid-plane)' },
      { key: 'closed', kind: 'bool', label: 'Closed loop (≥3 profiles)' },
      { key: 'continuity', kind: 'select', label: 'Continuity', options: [
        { value: 'C0', label: 'C0 (position)' },
        { value: 'C1', label: 'C1 (tangent)' },
        { value: 'C2', label: 'C2 (curvature)' },
      ] },
    ],
  },
  {
    op: 'variable_radius_fillet',
    label: 'Var. fillet',
    icon: Aperture,
    defaults: { target_id: '', edges: [] },
    fields: [
      { key: 'target_id', kind: 'feature_picker', label: 'Target body' },
      { key: 'edges', kind: 'edge_radius_list', label: 'Picked edges + radii' },
    ],
  },
  {
    op: 'network_srf',
    label: 'NetworkSrf',
    icon: Layers3,
    defaults: { u_curves: [], v_curves: [], continuity: 'C1' },
    fields: [
      { key: 'u_curves', kind: 'sketch_path_list', label: 'U-direction sketches (≥2)' },
      { key: 'v_curves', kind: 'sketch_path_list', label: 'V-direction sketches (≥2)' },
      { key: 'continuity', kind: 'select', label: 'Continuity', options: [
        { value: 'C0', label: 'C0 (position)' },
        { value: 'C1', label: 'C1 (tangent)' },
        { value: 'C2', label: 'C2 (curvature)' },
      ] },
    ],
  },
  {
    op: 'blend_srf',
    label: 'BlendSrf',
    icon: Waves,
    defaults: { target_id: '', edge1_id: -1, edge2_id: -1, continuity: 'G1' },
    fields: [
      { key: 'target_id', kind: 'feature_picker', label: 'Target body' },
      { key: 'edge1_id', kind: 'number', label: 'Edge 1 id', step: 1 },
      { key: 'edge2_id', kind: 'number', label: 'Edge 2 id', step: 1 },
      { key: 'continuity', kind: 'select', label: 'Continuity', options: [
        { value: 'G0', label: 'G0 (position)' },
        { value: 'G1', label: 'G1 (tangent)' },
        { value: 'G2', label: 'G2 (curvature)' },
      ] },
    ],
  },
  // NURBS booleans v1 — T6: to_solid + boolean inspector entries
  {
    op: 'to_solid',
    label: 'To Solid',
    icon: Box,
    defaults: { target_id: '', tolerance: 1e-6 },
    fields: [
      { key: 'target_id', kind: 'feature_picker', label: 'Surface body to cap' },
      { key: 'tolerance', kind: 'number', label: 'Sewing tolerance (mm)', min: 1e-9, step: 1e-7 },
    ],
  },
  {
    op: 'boolean',
    label: 'Boolean',
    icon: Combine,
    defaults: { target_a_id: '', target_b_id: '', kind: 'cut' },
    fields: [
      { key: 'target_a_id', kind: 'feature_picker', label: 'A (kept on cut)' },
      { key: 'target_b_id', kind: 'feature_picker', label: 'B (subtracted on cut)' },
      { key: 'kind', kind: 'select', label: 'Operation', options: [
        { value: 'cut',    label: 'Cut (A − B)' },
        { value: 'fuse',   label: 'Fuse (A ∪ B)' },
        { value: 'common', label: 'Common (A ∩ B)' },
      ] },
    ],
  },
  // NURBS Phase 4 C1-T4 — surface_boolean inspector entry.
  //
  // Conceptual sibling to `boolean` (solid CSG) but works directly on
  // Face / Shell / Solid operands — no feature_to_solid pre-step needed.
  // Returns a compound of trimmed face fragments rather than a closed solid.
  // Ideal for jewelry-CAD surface-direct workflows (blend cut by sweep, etc.).
  //
  // Differences vs `boolean`:
  //   - Accepts any topology (Face / Shell / Solid) — no solid enforcement.
  //   - Returns a compound of trimmed fragments, not a closed solid.
  //   - `tolerance` tunes the BOPAlgo intersection tolerance (fuzziness).
  //   - `fuzzy_value` passes directly to BRepAlgoAPI_*::SetFuzzyValue when
  //     the binding exposes it; raise to 1e-3 if tangent-intersection face
  //     fragments go missing.
  //   - If the worker logs a C1-T10 escalation, the current WASM build does
  //     not support non-solid operands — fall back to feature_boolean with a
  //     feature_to_solid pre-pass.
  {
    op: 'surface_boolean',
    label: 'SurfaceBoolean',
    icon: Combine,
    defaults: { target_a_id: '', target_b_id: '', kind: 'cut', tolerance: 1e-3 },
    caption: (
      'Surface-direct boolean — accepts Face/Shell/Solid operands without a ' +
      'feature_to_solid pre-step. Returns trimmed face fragments. ' +
      'Use when operating on raw NURBS surfaces (sweeps, blends, networks). ' +
      'For solid-on-solid CSG use the regular Boolean op instead.'
    ),
    fields: [
      { key: 'target_a_id', kind: 'feature_picker', label: 'A (surface/solid, kept on cut)' },
      { key: 'target_b_id', kind: 'feature_picker', label: 'B (surface/solid, tool on cut)' },
      { key: 'kind', kind: 'select', label: 'Operation', options: [
        { value: 'cut',    label: 'Cut (A − B)' },
        { value: 'fuse',   label: 'Fuse (A ∪ B)' },
        { value: 'common', label: 'Common (A ∩ B)' },
      ] },
      { key: 'tolerance', kind: 'number', label: 'Tolerance (mm)', min: 1e-9, step: 1e-4 },
      { key: 'fuzzy_value', kind: 'number', label: 'Fuzzy value (optional)', min: 0, step: 1e-4 },
    ],
  },
  // Slicing v0.2 — plane cross-section via BRepAlgoAPI_Section.
  // Returns a compound of intersection edges (1D outline, not a solid).
  // Inspector: target solid picker + plane point/normal xyz inputs.
  // Section-plane gumball is deferred to v0.3 (TODO: add drag-to-reposition
  // gumball in Gumball.jsx that snaps to face plane when armed).
  {
    op: 'section',
    label: 'Section',
    icon: Scissors,
    defaults: {
      target_solid_ref: '',
      plane: { point: [0, 0, 0], normal: [0, 0, 1] },
    },
    fields: [
      { key: 'target_solid_ref', kind: 'feature_picker', label: 'Target solid' },
      { key: 'plane.point[0]',  kind: 'number', label: 'Plane point X (mm)' },
      { key: 'plane.point[1]',  kind: 'number', label: 'Plane point Y (mm)' },
      { key: 'plane.point[2]',  kind: 'number', label: 'Plane point Z (mm)' },
      { key: 'plane.normal[0]', kind: 'number', label: 'Normal X' },
      { key: 'plane.normal[1]', kind: 'number', label: 'Normal Y' },
      { key: 'plane.normal[2]', kind: 'number', label: 'Normal Z' },
    ],
  },
  // Quad remesh v1 — Instant Meshes subprocess (MIT).
  // Remeshes a triangle mesh into a quad-dominant topology.
  // Requires the `instant-meshes` binary on PATH; degrades gracefully when absent.
  {
    op: 'quad_remesh',
    label: 'Quad Remesh',
    icon: Grid3x3,
    defaults: {
      target_feature_ref:  '',
      target_vertex_count: 5000,
      crease_angle_deg:    20,
      align_to_boundary:   true,
      smoothness_iters:    2,
    },
    fields: [
      { key: 'target_feature_ref',  kind: 'feature_picker', label: 'Source mesh / solid' },
      { key: 'target_vertex_count', kind: 'number', label: 'Target vertex count',   min: 1, step: 500 },
      { key: 'crease_angle_deg',    kind: 'number', label: 'Crease angle (°)',       min: 0, max: 180, step: 1 },
      { key: 'smoothness_iters',    kind: 'number', label: 'Smoothing iterations',  min: 0, max: 6, step: 1 },
      { key: 'align_to_boundary',   kind: 'boolean', label: 'Align to boundary' },
    ],
  },
  // NURBS Phase 4 C4 — curvature comb overlay (visualisation-only).
  // GeomAbs_G3 doesn't exist in stock OCCT — overlay lets users EYEBALL
  // G3 continuity at face junctions instead of enforcing it algorithmically.
  {
    op: 'surface_curvature_combs',
    label: 'CurvatureCombs',
    icon: Waves,
    defaults: {
      target_feature_ref: '',
      target_face_name: '',
      uv_density: 0.1,
      scale_factor: 10,
      show_combs: true,
    },
    caption: (
      'Curvature-comb overlay — renders principal-curvature combs on NURBS faces ' +
      '(blue=concave, red=convex, white=flat). ' +
      'Use to eyeball G2/G3 continuity at face junctions. ' +
      'Viz-only: stock OCCT has no GeomAbs_G3.'
    ),
    fields: [
      { key: 'target_feature_ref', kind: 'feature_picker', label: 'Target surface/solid' },
      { key: 'target_face_name',   kind: 'text',    label: 'Face name (blank = all faces)' },
      { key: 'uv_density',         kind: 'number',  label: 'UV density', min: 0.01, max: 0.5, step: 0.01 },
      { key: 'scale_factor',       kind: 'number',  label: 'Scale factor', min: 0.1, step: 1 },
      { key: 'show_combs',         kind: 'boolean', label: 'Show combs' },
    ],
  },
  // ── Jewelry ──────────────────────────────────────────────────────────────
  {
    op: 'gemstone',
    label: 'Gemstone',
    icon: Disc,
    defaults: {
      cut: 'round_brilliant',
      diameter_mm: 6.5,
      material: 'diamond',
    },
    fields: [
      { key: 'cut', kind: 'select', label: 'Cut', options: [
        { value: 'round_brilliant', label: 'Round brilliant' },
        { value: 'princess',        label: 'Princess' },
        { value: 'oval',            label: 'Oval' },
        { value: 'emerald',         label: 'Emerald' },
        { value: 'marquise',        label: 'Marquise' },
        { value: 'pear',            label: 'Pear' },
        { value: 'cushion',         label: 'Cushion' },
      ] },
      { key: 'diameter_mm',         kind: 'number',  label: 'Diameter / long-axis (mm)', min: 0.5 },
      { key: 'material',            kind: 'text',    label: 'Material' },
      { key: 'table_pct',           kind: 'number',  label: 'Table %',        min: 30, max: 90 },
      { key: 'crown_angle_deg',     kind: 'number',  label: 'Crown angle (°)', min: 10, max: 50 },
      { key: 'pavilion_angle_deg',  kind: 'number',  label: 'Pavilion angle (°)', min: 30, max: 55 },
      { key: 'girdle_pct',          kind: 'number',  label: 'Girdle %',        min: 0.5, max: 10 },
    ],
  },
  {
    op: 'gem_seat',
    label: 'Gem seat',
    icon: Disc,
    defaults: {
      cut: 'round_brilliant',
      diameter_mm: 6.5,
      girdle_clearance_mm: 0.05,
      through_hole: false,
    },
    caption: (
      'Gem-seat cutter solid: bearing cone + girdle ledge + crown relief. ' +
      'Subtract from host solid with a boolean cut to set the stone.'
    ),
    fields: [
      { key: 'cut', kind: 'select', label: 'Cut', options: [
        { value: 'round_brilliant', label: 'Round brilliant' },
        { value: 'princess',        label: 'Princess' },
        { value: 'oval',            label: 'Oval' },
        { value: 'emerald',         label: 'Emerald' },
        { value: 'marquise',        label: 'Marquise' },
        { value: 'pear',            label: 'Pear' },
        { value: 'cushion',         label: 'Cushion' },
      ] },
      { key: 'diameter_mm',          kind: 'number',  label: 'Diameter / long-axis (mm)', min: 0.5 },
      { key: 'girdle_clearance_mm',  kind: 'number',  label: 'Girdle clearance (mm)', min: 0, step: 0.01 },
      { key: 'culet_clearance_mm',   kind: 'number',  label: 'Culet clearance (mm)',  min: 0, step: 0.01 },
      { key: 'crown_relief_mm',      kind: 'number',  label: 'Crown relief (mm)',     min: 0, step: 0.05 },
      { key: 'through_hole',         kind: 'boolean', label: 'Through-hole for light' },
    ],
  },
]

const KIND_BY_OP = Object.fromEntries(FEATURE_KINDS.map((k) => [k.op, k]))

const FEATURE_CATEGORIES = [
  { id: 'sketch',   label: 'Sketch-based',  ops: ['pad', 'boss_with_draft', 'pocket', 'cut_from_sketch', 'revolve', 'hole', 'hole_pattern'] },
  { id: 'modify',   label: 'Modify',        ops: ['fillet', 'chamfer', 'shell', 'push_pull', 'variable_radius_fillet', 'to_solid', 'boolean', 'section', 'quad_remesh'] },
  { id: 'pattern',  label: 'Pattern',       ops: ['linear_pattern', 'polar_pattern', 'mirror_pattern'] },
  { id: 'surface',  label: 'Surfacing',     ops: ['sweep1', 'sweep2', 'loft', 'network_srf', 'blend_srf', 'surface_boolean', 'surface_curvature_combs'] },
  { id: 'jewelry',  label: 'Jewelry',       ops: ['gemstone', 'gem_seat'] },
]

const DEBOUNCE_MS = 300

// Click-outside + Escape dismiss for popovers. Mirrors the pattern in
// ChatPanel.jsx so behaviour is consistent across the app.
function useClickOutside(ref, onOutside, enabled) {
  useEffect(() => {
    if (!enabled) return
    function handle(e) {
      if (ref.current && !ref.current.contains(e.target)) onOutside()
    }
    function escListener(e) { if (e.key === 'Escape') onOutside() }
    document.addEventListener('mousedown', handle)
    document.addEventListener('keydown', escListener)
    return () => {
      document.removeEventListener('mousedown', handle)
      document.removeEventListener('keydown', escListener)
    }
  }, [ref, onOutside, enabled])
}

// ---------------------------------------------------------------------------
// Component.

export default function FeatureView({
  parsedFeature,            // current FeatureTree (from store.currentFeature)
  files,                    // file rows for the project (sketch picker)
  onChangeTree,             // (nextTree) => void
  loadSketchContent,        // (path: string) => Promise<string>; returns sketch JSON
}) {
  const tree = parsedFeature?.features || []
  const fileName = parsedFeature?.name || 'Feature'
  const currentFile = useWorkspace((s) => s.currentFile)
  const currentFileId = useWorkspace((s) => s.currentFileId)

  // Selection / pick mode lives in the workspace store so other UI (chat,
  // future tools) can read it. We wire two-way binding here.
  const featureSelection = useWorkspace((s) => s.featureSelection)
  const featurePickMode = useWorkspace((s) => s.featurePickMode)
  const featurePickTarget = useWorkspace((s) => s.featurePickTarget)
  const setFeatureSelection = useWorkspace((s) => s.setFeatureSelection)
  const setFeaturePickMode = useWorkspace((s) => s.setFeaturePickMode)
  const clearFeatureSelection = useWorkspace((s) => s.clearFeatureSelection)
  const createSketchOnFace = useWorkspace((s) => s.createSketchOnFace)
  const selectFile = useWorkspace((s) => s.selectFile)

  // Selected feature in the timeline (by id).
  const [selectedId, setSelectedId] = useState(null)
  useEffect(() => {
    if (!selectedId && tree.length > 0) setSelectedId(tree[tree.length - 1]?.id)
  }, [tree, selectedId])

  // Cached evaluation results — survive across debounced re-runs so a brief
  // error doesn't wipe the viewport.
  const [meshes, setMeshes] = useState([])
  const [evalState, setEvalState] = useState({ loading: false, error: null, ms: null })
  const lastGoodMeshesRef = useRef([])

  const sketchCacheRef = useRef(new Map())
  useEffect(() => { sketchCacheRef.current = new Map() }, [files])

  // Track the structural fingerprint of the tree (op kinds + ids in order) so
  // we can clear selection only when topology actually changes — pure
  // parameter tweaks (e.g. tweaking a height) preserve face/edge ids and
  // keep selections valid.
  const lastStructuralKeyRef = useRef('')
  useEffect(() => {
    const key = tree.map((n) => `${n.op}:${n.id}`).join('|')
    if (key !== lastStructuralKeyRef.current) {
      if (lastStructuralKeyRef.current !== '') {
        // Avoid clearing on the very first render — only on subsequent edits.
        clearFeatureSelection()
      }
      lastStructuralKeyRef.current = key
    }
  }, [tree, clearFeatureSelection])

  // Debounced re-evaluation pipeline.
  const debounceRef = useRef(null)
  const seqRef = useRef(0)

  const triggerEvaluate = useCallback(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    const seq = ++seqRef.current
    debounceRef.current = setTimeout(async () => {
      const referenced = new Set()
      for (const node of tree) {
        if (node.sketch_path) referenced.add(node.sketch_path)
      }
      const sketches = {}
      for (const path of referenced) {
        try {
          if (sketchCacheRef.current.has(path)) {
            sketches[path] = sketchCacheRef.current.get(path)
            continue
          }
          const content = loadSketchContent
            ? await loadSketchContent(path)
            : null
          sketches[path] = content || ''
          sketchCacheRef.current.set(path, content || '')
        } catch (err) {
          sketches[path] = ''
        }
      }
      // For face-anchored sketches whose anchor is on the *current* feature
      // file, resolve the face's world frame before dispatch. We need a
      // partial evaluation up to the anchor feature node — the worker's
      // requestFaceOutline does that for us.
      for (const path of Object.keys(sketches)) {
        try {
          const obj = sketches[path] ? JSON.parse(sketches[path]) : null
          const plane = obj?.plane
          if (plane?.type === 'face' && plane.face_id != null && (plane.file_id == null || plane.file_id === currentFileId)) {
            // Slice the tree up to (and including) the anchor feature node so
            // the face id resolves against the body that produced it. If
            // feature_node_id is missing we just use the whole tree.
            let sliced = tree
            if (plane.feature_node_id) {
              const idx = tree.findIndex((n) => n.id === plane.feature_node_id)
              if (idx >= 0) sliced = tree.slice(0, idx + 1)
            }
            const result = await requestFaceOutline(sliced, sketches, plane.face_id)
            if (result && result.ok && result.frame) {
              const baked = { ...obj, plane: { ...plane, frame: result.frame } }
              sketches[path] = JSON.stringify(baked)
            }
          }
        } catch { /* tolerate */ }
      }
      setEvalState((s) => ({ ...s, loading: true, error: null }))
      const t0 = performance.now()
      const result = await runFeatures(tree, sketches)
      const ms = Math.round(performance.now() - t0)
      if (seq !== seqRef.current) return
      if (result.stale) return
      if (result.error) {
        setEvalState({ loading: false, error: result.error, ms })
        if (result.partial) {
          const fallback = [{ id: 'partial', mesh: result.partial }]
          setMeshes(fallback)
        }
        return
      }
      const next = (result.meshes || []).map((m, i) => ({
        id: m.id || `body-${i}`,
        mesh: m,
      }))
      lastGoodMeshesRef.current = next
      setMeshes(next)
      setEvalState({ loading: false, error: null, ms })
    }, DEBOUNCE_MS)
  }, [tree, loadSketchContent])

  useEffect(() => { prewarmOcct() }, [])

  useEffect(() => {
    triggerEvaluate()
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current) }
  }, [parsedFeature, triggerEvaluate])

  // ---- Tree mutations ----
  const updateTree = useCallback((mutator) => {
    const nextFeatures = mutator(tree)
    onChangeTree?.({
      ...parsedFeature,
      features: Array.isArray(nextFeatures) ? nextFeatures : [],
    })
  }, [tree, parsedFeature, onChangeTree])

  const addFeature = useCallback((op) => {
    const kind = KIND_BY_OP[op]
    if (!kind) return
    const id = newFeatureId(op)
    const node = { id, op, ...kind.defaults }
    if (['pocket', 'fillet', 'chamfer', 'shell', 'hole'].includes(op)) {
      const lastBody = [...tree].reverse().find((n) => n.op === 'pad' || n.op === 'revolve')
      if (lastBody) node.target_id = lastBody.id
    }
    updateTree((arr) => [...arr, node])
    setSelectedId(id)
  }, [tree, updateTree])

  const removeFeature = useCallback((id) => {
    updateTree((arr) => arr.filter((n) => n.id !== id))
    if (selectedId === id) setSelectedId(null)
  }, [updateTree, selectedId])

  const moveFeature = useCallback((id, dir) => {
    updateTree((arr) => {
      const idx = arr.findIndex((n) => n.id === id)
      if (idx < 0) return arr
      const j = dir === 'up' ? idx - 1 : idx + 1
      if (j < 0 || j >= arr.length) return arr
      const out = arr.slice()
      const tmp = out[idx]; out[idx] = out[j]; out[j] = tmp
      return out
    })
  }, [updateTree])

  const patchFeature = useCallback((id, patch) => {
    updateTree((arr) => arr.map((n) => n.id === id ? { ...n, ...patch } : n))
  }, [updateTree])

  // ---- Push/pull commit: append a push_pull feature node ----
  const onPushPullCommit = useCallback(({ partId, faceId, faceName, distance }) => {
    if (Math.abs(distance) < 0.05) return
    void partId
    const id = newFeatureId('push_pull')
    // T5: dual-write face_name (persistent) + face_id (legacy fallback).
    const node = { id, op: 'push_pull', face_id: faceId, distance }
    if (faceName) node.face_name = faceName
    updateTree((arr) => [...arr, node])
    setSelectedId(id)
    setFeaturePickMode(null)
  }, [updateTree, setFeaturePickMode])

  // ---- Sketch-on-face: handle a one-shot face pick that creates a sketch ----
  // T5: onFacePicked now receives { id, name, partId } from FeatureRenderer
  // (name is the persistent face name, id is the integer id).
  const onFacePicked = useCallback(async (pickArg, legacyPartId) => {
    // Support both legacy (faceId, partId) and new ({ id, name, partId }) shapes.
    let faceId, faceName, partId
    if (pickArg && typeof pickArg === 'object' && 'id' in pickArg) {
      faceId   = pickArg.id
      faceName = pickArg.name || ''
      partId   = pickArg.partId
    } else {
      faceId   = pickArg
      faceName = ''
      partId   = legacyPartId
    }
    void partId
    const mode = featurePickMode
    const target = featurePickTarget
    if (mode === 'sketch_on_face') {
      // Find the parent feature node that produced this body. v1 just uses
      // the latest pad/revolve as the anchor — multi-body trees aren't a v1
      // goal anyway.
      const anchor = [...tree].reverse().find((n) => n.op === 'pad' || n.op === 'revolve')
      const name = window.prompt('Sketch name', 'sketch-on-face.sketch')
      if (!name) {
        setFeaturePickMode(null)
        return
      }
      const created = await createSketchOnFace({
        parentId: currentFile?.parent_id || null,
        name: name.endsWith('.sketch') ? name : `${name}.sketch`,
        featureFileId: currentFileId,
        featureNodeId: anchor?.id || null,
        faceId,
      })
      setFeaturePickMode(null)
      if (created) await selectFile(created.id)
      return
    }
    if (mode === 'one_shot_face' && target) {
      // Fill the target field on the target feature with the picked face id.
      // T5: also dual-write the persistent name into a companion _name field
      // (e.g. target_face_id → target_face_name, face_id → face_name).
      if (target.accept === 'face_multi') {
        patchFeature(target.featureId, {
          [target.fieldKey]: Array.from(new Set([...(_arrayField(tree, target.featureId, target.fieldKey)), faceId])),
        })
      } else {
        const patch = { [target.fieldKey]: faceId }
        // Derive companion name key: target_face_id → target_face_name, face_id → face_name
        const nameKey = target.fieldKey.replace(/_id$/, '_name')
        if (faceName && nameKey !== target.fieldKey) patch[nameKey] = faceName
        patchFeature(target.featureId, patch)
      }
      setFeaturePickMode(null)
    }
    if (mode === 'one_shot_axis' || mode === 'one_shot_plane') {
      // Treat axis/plane picks: fill with the face id (numeric) for plane,
      // and reject for axis (the user should pick an edge for axis).
      if (mode === 'one_shot_plane' && target) {
        const patch = { [target.fieldKey]: faceId }
        // T6: dual-write plane_face_name when picking a face as the mirror plane.
        if (faceName && target.fieldKey === 'plane') patch.plane_face_name = faceName
        patchFeature(target.featureId, patch)
        setFeaturePickMode(null)
      }
    }
  }, [featurePickMode, featurePickTarget, tree, createSketchOnFace, currentFile, currentFileId, patchFeature, setFeaturePickMode, selectFile])

  // ---- Watch selection updates: if the active inspector has a one-shot pick
  // armed for an edge or edge_multi field, write the picked id back. ----
  useEffect(() => {
    if (!featurePickMode || !featurePickTarget) return
    if (featurePickMode === 'one_shot_edge') {
      // Take the most recently added edge id from the selection set.
      const list = Array.from(featureSelection.edgeIds || []).map((k) => Number(k.split('|')[1]))
      if (list.length === 0) return
      const newest = list[list.length - 1]
      const t = featurePickTarget
      if (t.accept === 'edge_multi') {
        patchFeature(t.featureId, (prev) => prev) // noop, we update via callback
        const nodeIdx = tree.findIndex((n) => n.id === t.featureId)
        if (nodeIdx >= 0) {
          const cur = tree[nodeIdx]
          const ids = Array.isArray(cur.edge_ids) ? cur.edge_ids : []
          if (!ids.includes(newest)) {
            patchFeature(t.featureId, { edge_ids: [...ids, newest], edge_filter: 'manual' })
          }
        }
      } else {
        patchFeature(t.featureId, { [t.fieldKey]: newest })
      }
      setFeaturePickMode(null)
    }
    if (featurePickMode === 'one_shot_axis') {
      const list = Array.from(featureSelection.edgeIds || []).map((k) => Number(k.split('|')[1]))
      if (list.length === 0) return
      const newest = list[list.length - 1]
      patchFeature(featurePickTarget.featureId, { [featurePickTarget.fieldKey]: newest })
      setFeaturePickMode(null)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [featureSelection])

  // ---- Auto-sync selection → active feature's edge/face fields when in
  //      multi-pick (face / edge) mode. ----
  useEffect(() => {
    if (featurePickMode !== 'edge' && featurePickMode !== 'face') return
    const active = tree.find((n) => n.id === selectedId)
    if (!active) return
    if (featurePickMode === 'edge' && (active.op === 'fillet' || active.op === 'chamfer')) {
      const ids = Array.from(featureSelection.edgeIds || []).map((k) => Number(k.split('|')[1]))
      // Only update if the array actually changed.
      const cur = Array.isArray(active.edge_ids) ? active.edge_ids : []
      if (cur.length !== ids.length || cur.some((v, i) => v !== ids[i])) {
        patchFeature(active.id, { edge_ids: ids, edge_filter: 'manual' })
      }
    } else if (featurePickMode === 'face' && active.op === 'shell') {
      const ids = Array.from(featureSelection.faceIds || []).map((k) => Number(k.split('|')[1]))
      const cur = Array.isArray(active.face_ids) ? active.face_ids : []
      if (cur.length !== ids.length || cur.some((v, i) => v !== ids[i])) {
        patchFeature(active.id, { face_ids: ids })
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [featureSelection, featurePickMode, selectedId])

  // ---- Derived UI state ----
  const sketchFiles = useMemo(() => {
    return (files || []).filter((f) => {
      if (!f) return false
      if (f.kind === 'sketch') return true
      const n = (f.name || '').toLowerCase()
      return n.endsWith('.sketch')
    })
  }, [files])

  const sketchPaths = useMemo(() => {
    const byId = new Map((files || []).map((f) => [f.id, f]))
    function pathOf(f) {
      const parts = []
      let cur = f
      let safety = 0
      while (cur && safety++ < 64) {
        parts.unshift(cur.name)
        if (!cur.parent_id) break
        cur = byId.get(cur.parent_id)
      }
      return '/' + parts.join('/')
    }
    return sketchFiles.map((f) => ({ id: f.id, path: pathOf(f), name: f.name }))
  }, [files, sketchFiles])

  const selectedFeature = useMemo(
    () => tree.find((n) => n.id === selectedId) || null,
    [tree, selectedId],
  )

  const vertexCount = useMemo(() => {
    let n = 0
    for (const m of meshes) {
      const v = m?.mesh?.vertices
      if (v) n += v.length / 3
    }
    return n
  }, [meshes])

  // ---- Render ----
  const selCount = featureSelection.faceIds.size + featureSelection.edgeIds.size
  return (
    <div className="flex-1 min-h-0 flex flex-col bg-ink-950 text-ink-100">
      {/* Unified toolbar — add-feature popover + file name + timeline chips
          on the left; pick-mode controls on the right. */}
      <div className="border-b border-ink-800 bg-ink-900 px-3 h-11 flex items-center gap-2">
        <AddFeaturePopover onPick={(op) => addFeature(op)} />

        <span className="w-px h-5 bg-ink-800 mx-0.5 flex-shrink-0" />

        <span
          className="text-xs text-ink-400 truncate max-w-[160px] flex-shrink-0"
          title={fileName}
        >
          {fileName}
        </span>

        {/* Timeline — scroll horizontally if it gets long. */}
        <div
          className="flex-1 min-w-0 flex items-center gap-1 overflow-x-auto scrollbar-thin"
          title={tree.length > 1 ? 'Selections may reset after structural changes.' : undefined}
        >
          {tree.length === 0 ? (
            <span className="text-xs text-ink-500 italic">
              No features yet — click <span className="text-ink-300">Add feature</span> to start.
            </span>
          ) : (
            tree.map((node, idx) => {
              const kind = KIND_BY_OP[node.op]
              const Icon = kind?.icon || Box
              const isSel = node.id === selectedId
              return (
                <div key={node.id} className="flex items-center gap-1 flex-shrink-0">
                  {idx > 0 && <ChevronRight size={11} className="text-ink-600" />}
                  <button
                    type="button"
                    onClick={() => setSelectedId(node.id)}
                    onContextMenu={(ev) => {
                      ev.preventDefault()
                      if (confirm(`Delete ${kind?.label || node.op} '${node.id}'?`)) removeFeature(node.id)
                    }}
                    className={`group relative inline-flex items-center gap-1.5 pl-1.5 pr-2 py-1 rounded-md border text-xs transition-colors
                      ${isSel
                        ? 'border-kerf-300/60 bg-kerf-300/10 text-kerf-100 shadow-[0_0_0_1px_rgba(255,214,51,0.15)]'
                        : 'border-ink-800 bg-ink-850 text-ink-200 hover:border-ink-600 hover:bg-ink-800'}`}
                    title={`${kind?.label || node.op} · right-click to delete`}
                  >
                    <span
                      className={`inline-flex items-center justify-center w-4 h-4 rounded text-[10px] font-mono leading-none
                        ${isSel ? 'bg-kerf-300/30 text-kerf-100' : 'bg-ink-800 text-ink-400'}`}
                    >
                      {idx + 1}
                    </span>
                    <Icon size={12} className={isSel ? 'text-kerf-200' : 'text-ink-300'} />
                    <span>{kind?.label || node.op}</span>
                    {isSel && (
                      <span
                        role="button"
                        aria-label="Delete feature"
                        onClick={(ev) => {
                          ev.stopPropagation()
                          if (confirm(`Delete ${kind?.label || node.op} '${node.id}'?`)) removeFeature(node.id)
                        }}
                        className="ml-0.5 -mr-0.5 inline-flex items-center justify-center w-4 h-4 rounded text-ink-400 hover:text-red-300 hover:bg-red-900/30"
                      >
                        <X size={10} />
                      </span>
                    )}
                  </button>
                </div>
              )
            })
          )}
        </div>

        {/* Pick-mode controls (right side). */}
        <div className="flex items-center gap-1 flex-shrink-0">
          <ModeBtn
            active={featurePickMode === 'face'}
            onClick={() => setFeaturePickMode(featurePickMode === 'face' ? null : 'face')}
            icon={Pointer}
            label="Faces"
            title="Click faces to select. Shift-click to add. Drives Shell/face_ids of the active feature."
          />
          <ModeBtn
            active={featurePickMode === 'edge'}
            onClick={() => setFeaturePickMode(featurePickMode === 'edge' ? null : 'edge')}
            icon={Pointer}
            label="Edges"
            title="Click edges to select. Shift-click to add. Drives Fillet/Chamfer manual edge_ids."
          />
          <span className="w-px h-5 bg-ink-800 mx-1" />
          <ModeBtn
            active={featurePickMode === 'pushpull'}
            onClick={() => setFeaturePickMode(featurePickMode === 'pushpull' ? null : 'pushpull')}
            icon={Move}
            label="Push/Pull"
            title="Drag a face along its normal. Release to commit a Pad/Pocket."
          />
          <ModeBtn
            active={featurePickMode === 'sketch_on_face'}
            onClick={() => setFeaturePickMode(featurePickMode === 'sketch_on_face' ? null : 'sketch_on_face')}
            icon={PencilLine}
            label="Sketch on face"
            title="Click a planar face to create a new sketch on it."
          />
        </div>
      </div>

      {/* Main: viewport + inspector. */}
      <div className="flex-1 min-h-0 grid" style={{ gridTemplateColumns: '1fr 280px' }}>
        <main className="relative min-h-0 min-w-0">
          <FeatureRenderer
            meshes={meshes}
            selection={featureSelection}
            pickMode={featurePickMode}
            onSelectionChange={setFeatureSelection}
            onFacePick={onFacePicked}
            onPushPullCommit={onPushPullCommit}
            className="w-full h-full"
          />
          {evalState.loading && (
            <div className="absolute top-3 left-3 inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-ink-900/85 backdrop-blur border border-ink-700 text-[11px] text-ink-200 shadow-lg shadow-black/30">
              <Loader2 size={11} className="animate-spin text-kerf-300" />
              <span>Evaluating</span>
            </div>
          )}
          {featurePickMode && (
            <div className="absolute top-3 right-3 inline-flex items-center gap-1.5 pl-2 pr-1 py-1 rounded-md bg-kerf-300/15 backdrop-blur border border-kerf-300/40 text-[11px] text-kerf-100 shadow-lg shadow-black/30">
              <Crosshair size={11} />
              <span>
                {featurePickMode === 'pushpull' && 'Push/Pull · drag a face'}
                {featurePickMode === 'sketch_on_face' && 'Click a planar face'}
                {featurePickMode === 'face' && 'Click faces · shift to add'}
                {featurePickMode === 'edge' && 'Click edges · shift to add'}
                {featurePickMode === 'one_shot_face' && 'Pick a face'}
                {featurePickMode === 'one_shot_edge' && 'Pick an edge'}
                {featurePickMode === 'one_shot_axis' && 'Pick an edge for axis'}
                {featurePickMode === 'one_shot_plane' && 'Pick a face for plane'}
              </span>
              <button
                type="button"
                onClick={() => setFeaturePickMode(null)}
                className="ml-0.5 inline-flex items-center justify-center w-4 h-4 rounded text-kerf-200 hover:text-white hover:bg-kerf-300/20"
                title="Cancel pick"
              >
                <X size={10} />
              </button>
            </div>
          )}
        </main>

        {/* Right: inspector */}
        <aside className="border-l border-ink-800 bg-ink-900/60 min-h-0 overflow-y-auto">
          {!selectedFeature ? (
            <div className="p-4 text-xs text-ink-500 italic">
              Select a feature in the timeline to edit its parameters.
            </div>
          ) : (
            <FeatureInspector
              feature={selectedFeature}
              tree={tree}
              sketchPaths={sketchPaths}
              selection={featureSelection}
              pickMode={featurePickMode}
              setFeaturePickMode={setFeaturePickMode}
              setFeatureSelection={setFeatureSelection}
              onPatch={(patch) => patchFeature(selectedFeature.id, patch)}
              onMoveUp={() => moveFeature(selectedFeature.id, 'up')}
              onMoveDown={() => moveFeature(selectedFeature.id, 'down')}
              onDelete={() => removeFeature(selectedFeature.id)}
            />
          )}
        </aside>
      </div>

      {/* Bottom: status bar — eval/error left, selection summary middle,
          re-evaluate right. */}
      <div className="flex items-center gap-3 px-3 h-7 border-t border-ink-800 bg-ink-900 text-[11px] font-mono text-ink-500 flex-shrink-0">
        {evalState.error ? (
          <span className="inline-flex items-center gap-1.5 text-red-400 min-w-0">
            <AlertTriangle size={11} className="flex-shrink-0" />
            <span className="truncate" title={evalState.error}>{evalState.error}</span>
          </span>
        ) : (
          <span className="inline-flex items-center gap-1.5">
            <span className="text-ink-300">{vertexCount.toLocaleString()}</span>
            <span className="text-ink-500">vertices</span>
            <span className="text-ink-700">·</span>
            <span className="text-ink-300">{meshes.length}</span>
            <span className="text-ink-500">{meshes.length === 1 ? 'body' : 'bodies'}</span>
            {evalState.ms != null && (
              <>
                <span className="text-ink-700">·</span>
                <span>{evalState.ms}ms</span>
              </>
            )}
          </span>
        )}
        <div className="flex-1" />
        {selCount > 0 && (
          <>
            <span className="inline-flex items-center gap-1.5">
              <span className="text-ink-500">Sel</span>
              <span className="text-ink-300">{featureSelection.faceIds.size}</span>
              <span className="text-ink-500">{featureSelection.faceIds.size === 1 ? 'face' : 'faces'}</span>
              <span className="text-ink-700">·</span>
              <span className="text-ink-300">{featureSelection.edgeIds.size}</span>
              <span className="text-ink-500">{featureSelection.edgeIds.size === 1 ? 'edge' : 'edges'}</span>
            </span>
            <button
              type="button"
              onClick={() => clearFeatureSelection()}
              className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-ink-400 hover:text-kerf-300 hover:bg-ink-800"
              title="Clear viewport selection"
            >
              clear
            </button>
            <span className="w-px h-4 bg-ink-800" />
          </>
        )}
        <button
          type="button"
          onClick={() => triggerEvaluate()}
          className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-ink-300 hover:text-kerf-300 hover:bg-ink-800"
          title="Force re-evaluation"
        >
          <Play size={10} />
          <span>Re-evaluate</span>
        </button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Add-feature popover. Single button replaces the 14-icon kitchen-sink; opens
// a panel with FEATURE_CATEGORIES groups and a 3-column grid of icon tiles.

function AddFeaturePopover({ onPick }) {
  const [open, setOpen] = useState(false)
  const wrapRef = useRef(null)
  useClickOutside(wrapRef, () => setOpen(false), open)

  return (
    <div ref={wrapRef} className="relative flex-shrink-0">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={`inline-flex items-center gap-1.5 pl-2 pr-2.5 py-1.5 rounded-md border text-xs font-medium transition-colors
          ${open
            ? 'border-kerf-300/60 bg-kerf-300/15 text-kerf-100'
            : 'border-ink-700 bg-ink-850 text-ink-100 hover:bg-ink-800 hover:border-ink-600'}`}
        title="Add a feature to the timeline"
      >
        <Plus size={13} className={open ? 'text-kerf-200' : 'text-kerf-300'} />
        <span>Add feature</span>
        <ChevronDown
          size={11}
          className={`text-ink-400 transition-transform ${open ? 'rotate-180' : ''}`}
        />
      </button>

      {open && (
        <div
          className="absolute top-full left-0 mt-1.5 z-30 w-[420px] rounded-lg border border-ink-700 bg-ink-900 shadow-2xl shadow-black/60 overflow-hidden"
          role="menu"
        >
          <div className="max-h-[70vh] overflow-y-auto py-1.5">
            {FEATURE_CATEGORIES.map((cat, ci) => (
              <div key={cat.id} className={ci > 0 ? 'border-t border-ink-800 mt-1.5 pt-1.5' : ''}>
                <div className="px-3 pt-1.5 pb-1 text-[10px] uppercase tracking-wider text-ink-500 font-medium">
                  {cat.label}
                </div>
                <div className="grid grid-cols-3 gap-0.5 px-1.5 pb-1.5">
                  {cat.ops.map((op) => {
                    const k = KIND_BY_OP[op]
                    if (!k) return null
                    const Icon = k.icon
                    return (
                      <button
                        key={op}
                        type="button"
                        onClick={() => { onPick(op); setOpen(false) }}
                        className="group flex flex-col items-center gap-1 px-2 py-2.5 rounded-md text-ink-200 hover:bg-ink-800 hover:text-kerf-200 transition-colors"
                        title={`Add ${k.label}`}
                      >
                        <Icon size={18} className="text-ink-300 group-hover:text-kerf-300" />
                        <span className="text-[11px] leading-none">{k.label}</span>
                      </button>
                    )
                  })}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Right-pane inspector. Renders the field schema for the feature's op.

function FeatureInspector({
  feature,
  tree,
  sketchPaths,
  selection,
  pickMode,
  setFeaturePickMode,
  setFeatureSelection,
  onPatch,
  onMoveUp,
  onMoveDown,
  onDelete,
}) {
  const kind = KIND_BY_OP[feature.op]
  const bodyFeatures = useMemo(() => {
    const idx = tree.findIndex((n) => n.id === feature.id)
    if (idx < 0) return []
    return tree.slice(0, idx).filter((n) => n.op === 'pad' || n.op === 'revolve' || n.op === 'pocket' || n.op === 'fillet' || n.op === 'chamfer' || n.op === 'shell' || n.op === 'hole' || n.op === 'push_pull' || n.op === 'linear_pattern' || n.op === 'polar_pattern' || n.op === 'mirror_pattern')
  }, [tree, feature.id])

  if (!kind) {
    return (
      <div className="p-4 text-xs text-ink-500 italic">
        Unknown op: {feature.op}
      </div>
    )
  }
  const Icon = kind.icon

  return (
    <div className="flex flex-col">
      {/* Header — feature name + reorder + delete. */}
      <div className="sticky top-0 z-10 px-3 py-2.5 bg-ink-900 border-b border-ink-800 flex items-center gap-2">
        <span className="inline-flex items-center justify-center w-6 h-6 rounded bg-kerf-300/15 border border-kerf-300/30 flex-shrink-0">
          <Icon size={13} className="text-kerf-200" />
        </span>
        <div className="min-w-0 flex-1">
          <div className="text-sm font-medium text-ink-100 leading-tight">{kind.label}</div>
          <div className="text-[10px] text-ink-500 font-mono truncate" title={feature.id}>
            {feature.id}
          </div>
        </div>
        <div className="flex items-center gap-0.5 flex-shrink-0">
          <button
            type="button"
            onClick={onMoveUp}
            className="inline-flex items-center justify-center w-6 h-6 rounded text-ink-400 hover:text-kerf-300 hover:bg-ink-800"
            title="Move up in timeline"
          >
            <ChevronUp size={13} />
          </button>
          <button
            type="button"
            onClick={onMoveDown}
            className="inline-flex items-center justify-center w-6 h-6 rounded text-ink-400 hover:text-kerf-300 hover:bg-ink-800"
            title="Move down in timeline"
          >
            <ChevronDown size={13} />
          </button>
          <button
            type="button"
            onClick={onDelete}
            className="inline-flex items-center justify-center w-6 h-6 rounded text-ink-400 hover:text-red-300 hover:bg-red-900/25"
            title="Delete this feature"
          >
            <Trash2 size={12} />
          </button>
        </div>
      </div>

      {/* Body — field list. */}
      <div className="px-3 py-3 space-y-3">
      {kind.fields.map((field) => {
        if (field.showWhen && !field.showWhen(feature)) return null
        return (
          <div key={field.key} className="space-y-1.5">
            <label className="block text-[11px] font-medium text-ink-300">
              {field.label}
            </label>
            {field.kind === 'number' && (
              <input
                type="number"
                value={feature[field.key] ?? ''}
                onChange={(ev) => {
                  const v = ev.target.value === '' ? '' : Number(ev.target.value)
                  onPatch({ [field.key]: v })
                }}
                min={field.min}
                max={field.max}
                step={field.step ?? 'any'}
                className="w-full px-2 py-1 bg-ink-950 border border-ink-700 rounded text-xs font-mono
                           focus:outline-none focus:border-kerf-300/60"
              />
            )}
            {field.kind === 'select' && (
              <select
                value={feature[field.key] ?? field.options?.[0]?.value}
                onChange={(ev) => onPatch({ [field.key]: ev.target.value })}
                className="w-full px-2 py-1 bg-ink-950 border border-ink-700 rounded text-xs
                           focus:outline-none focus:border-kerf-300/60"
              >
                {(field.options || []).map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            )}
            {field.kind === 'sketch_picker' && (
              <select
                value={feature[field.key] ?? ''}
                onChange={(ev) => onPatch({ [field.key]: ev.target.value })}
                className="w-full px-2 py-1 bg-ink-950 border border-ink-700 rounded text-xs font-mono
                           focus:outline-none focus:border-kerf-300/60"
              >
                <option value="">— pick a sketch —</option>
                {sketchPaths.map((s) => (
                  <option key={s.id} value={s.path}>{s.path}</option>
                ))}
              </select>
            )}
            {field.kind === 'feature_picker' && (
              <select
                value={feature[field.key] ?? ''}
                onChange={(ev) => onPatch({ [field.key]: ev.target.value })}
                className="w-full px-2 py-1 bg-ink-950 border border-ink-700 rounded text-xs font-mono
                           focus:outline-none focus:border-kerf-300/60"
              >
                <option value="">— pick a feature —</option>
                {bodyFeatures.map((n) => (
                  <option key={n.id} value={n.id}>{n.id} ({n.op})</option>
                ))}
              </select>
            )}
            {field.kind === 'edge_picker' && (
              <EdgeIdsField
                value={feature[field.key] || []}
                onChange={(ids) => onPatch({ [field.key]: ids, edge_filter: 'manual' })}
                pickArmed={pickMode === 'edge'}
                onArmPick={() => setFeaturePickMode(pickMode === 'edge' ? null : 'edge')}
                selection={selection}
                setSelection={setFeatureSelection}
              />
            )}
            {field.kind === 'face_picker' && (
              <FaceIdsField
                value={feature[field.key] || []}
                onChange={(ids) => onPatch({ [field.key]: ids })}
                pickArmed={pickMode === 'face'}
                onArmPick={() => setFeaturePickMode(pickMode === 'face' ? null : 'face')}
                selection={selection}
                setSelection={setFeatureSelection}
              />
            )}
            {field.kind === 'face_picker_single' && (
              <SingleFaceIdField
                value={feature[field.key]}
                onChange={(id) => onPatch({ [field.key]: id })}
                onArmPick={() => setFeaturePickMode('one_shot_face', { featureId: feature.id, fieldKey: field.key, accept: 'face' })}
              />
            )}
            {field.kind === 'axis_picker' && (
              <AxisField
                value={feature[field.key]}
                onChange={(v) => onPatch({ [field.key]: v })}
                onArmPick={() => setFeaturePickMode('one_shot_axis', { featureId: feature.id, fieldKey: field.key, accept: 'edge' })}
              />
            )}
            {field.kind === 'plane_picker' && (
              <PlaneField
                value={feature[field.key]}
                onChange={(v) => onPatch({ [field.key]: v })}
                onArmPick={() => setFeaturePickMode('one_shot_plane', { featureId: feature.id, fieldKey: field.key, accept: 'face' })}
              />
            )}
            {field.kind === 'bool' && (
              <label className="flex items-center gap-2 px-2 py-1 bg-ink-950 border border-ink-700 rounded text-xs cursor-pointer">
                <input
                  type="checkbox"
                  checked={feature[field.key] === true}
                  onChange={(ev) => onPatch({ [field.key]: ev.target.checked })}
                />
                <span className="text-ink-300">{feature[field.key] === true ? 'on' : 'off'}</span>
              </label>
            )}
            {field.kind === 'sketch_path_list' && (
              <SketchPathListField
                value={feature[field.key] || []}
                onChange={(v) => onPatch({ [field.key]: v })}
                sketchPaths={sketchPaths}
              />
            )}
            {field.kind === 'edge_radius_list' && (
              <EdgeRadiusListField
                value={feature[field.key] || []}
                onChange={(v) => onPatch({ [field.key]: v })}
                pickArmed={pickMode === 'edge'}
                onArmPick={() => setFeaturePickMode(pickMode === 'edge' ? null : 'edge')}
                selection={selection}
                setSelection={setFeatureSelection}
              />
            )}
          </div>
        )
      })}
      {/* Caption — optional explanatory note for ops that benefit from one (e.g. surface_boolean). */}
      {kind.caption && (
        <div className="mx-3 mb-3 px-2 py-2 rounded bg-ink-800/60 border border-ink-700/50 text-[10px] text-ink-400 leading-relaxed">
          {kind.caption}
        </div>
      )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Selection-driven field components.

// SketchPathListField — ordered list of sketch paths (loft profiles, etc.).
// Add via the dropdown at the bottom; remove via the X on each row; reorder
// with the up/down arrows.
function SketchPathListField({ value, onChange, sketchPaths }) {
  const list = Array.isArray(value) ? value : []
  const remaining = sketchPaths.filter((s) => !list.includes(s.path))
  return (
    <div className="space-y-1">
      {list.length === 0 ? (
        <div className="text-[11px] text-ink-500 italic">No profiles yet — pick at least 2.</div>
      ) : (
        <div className="space-y-0.5">
          {list.map((p, i) => (
            <div key={`${p}-${i}`} className="flex items-center gap-1 px-1.5 py-1 bg-ink-950 border border-ink-700 rounded text-xs font-mono">
              <span className="text-ink-500 w-4 text-right">{i + 1}.</span>
              <span className="flex-1 truncate text-ink-200">{p}</span>
              <button type="button" disabled={i === 0}
                className="text-ink-500 hover:text-kerf-300 disabled:opacity-30"
                onClick={() => {
                  const next = [...list]; ;[next[i - 1], next[i]] = [next[i], next[i - 1]]; onChange(next)
                }}>
                <ChevronUp size={12} />
              </button>
              <button type="button" disabled={i === list.length - 1}
                className="text-ink-500 hover:text-kerf-300 disabled:opacity-30"
                onClick={() => {
                  const next = [...list]; ;[next[i + 1], next[i]] = [next[i], next[i + 1]]; onChange(next)
                }}>
                <ChevronDown size={12} />
              </button>
              <button type="button"
                className="text-ink-500 hover:text-red-400"
                onClick={() => onChange(list.filter((_, j) => j !== i))}>
                <Trash2 size={12} />
              </button>
            </div>
          ))}
        </div>
      )}
      {remaining.length > 0 && (
        <select
          value=""
          onChange={(ev) => { if (ev.target.value) onChange([...list, ev.target.value]) }}
          className="w-full px-2 py-1 bg-ink-950 border border-ink-700 rounded text-xs font-mono
                     focus:outline-none focus:border-kerf-300/60"
        >
          <option value="">— add a profile sketch —</option>
          {remaining.map((s) => (
            <option key={s.id} value={s.path}>{s.path}</option>
          ))}
        </select>
      )}
    </div>
  )
}

// EdgeRadiusListField — list of {edge_id, start_radius, end_radius} for the
// variable-radius fillet. v1 keeps it simple: each picked edge gets a start
// radius and an end radius (the worker fans these out into a 2-point param
// table at .at=0 and .at=1). Richer per-vertex point editing is a follow-up.
function EdgeRadiusListField({ value, onChange, pickArmed, onArmPick, selection }) {
  const rows = Array.isArray(value) ? value : []
  // Sync any newly-picked edges into the rows with default radii.
  const pickedSet = selection?.edges instanceof Set ? selection.edges : new Set()
  useEffect(() => {
    if (!pickArmed) return
    const known = new Set(rows.map((r) => r.edge_id))
    const additions = []
    for (const eid of pickedSet) {
      if (!known.has(eid)) additions.push({ edge_id: eid, radii: [{ at: 0, radius: 1 }, { at: 1, radius: 1 }] })
    }
    if (additions.length > 0) onChange([...rows, ...additions])
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pickedSet.size, pickArmed])
  return (
    <div className="space-y-1">
      {rows.length === 0 ? (
        <div className="text-[11px] text-ink-500 italic">Arm pick + click edges in viewport, or use the toggle below.</div>
      ) : (
        <div className="space-y-0.5">
          {rows.map((row, i) => {
            const start = row.radii?.[0]?.radius ?? 1
            const end = row.radii?.[row.radii.length - 1]?.radius ?? start
            return (
              <div key={row.edge_id} className="flex items-center gap-1 px-1.5 py-1 bg-ink-950 border border-ink-700 rounded text-[11px] font-mono">
                <span className="text-ink-500 w-12">edge {row.edge_id}</span>
                <input
                  type="number"
                  value={start}
                  step={0.1}
                  min={0.001}
                  onChange={(ev) => {
                    const v = Number(ev.target.value)
                    const next = [...rows]
                    next[i] = { ...row, radii: [{ at: 0, radius: v }, { at: 1, radius: end }] }
                    onChange(next)
                  }}
                  className="w-16 px-1 py-0.5 bg-ink-900 border border-ink-700 rounded"
                />
                <span className="text-ink-500">→</span>
                <input
                  type="number"
                  value={end}
                  step={0.1}
                  min={0.001}
                  onChange={(ev) => {
                    const v = Number(ev.target.value)
                    const next = [...rows]
                    next[i] = { ...row, radii: [{ at: 0, radius: start }, { at: 1, radius: v }] }
                    onChange(next)
                  }}
                  className="w-16 px-1 py-0.5 bg-ink-900 border border-ink-700 rounded"
                />
                <button type="button"
                  className="text-ink-500 hover:text-red-400 ml-auto"
                  onClick={() => onChange(rows.filter((_, j) => j !== i))}>
                  <Trash2 size={11} />
                </button>
              </div>
            )
          })}
        </div>
      )}
      <button
        type="button"
        onClick={onArmPick}
        className={`w-full px-2 py-1 rounded text-xs border transition-colors ${
          pickArmed
            ? 'bg-kerf-300/15 border-kerf-300/40 text-kerf-200'
            : 'bg-ink-950 border-ink-700 text-ink-400 hover:text-kerf-300'
        }`}
      >
        {pickArmed ? 'Click edges in viewport (Esc to stop)' : 'Pick edges'}
      </button>
    </div>
  )
}

function EdgeIdsField({ value, onChange, pickArmed, onArmPick, selection, setSelection }) {
  const ids = Array.isArray(value) ? value : []
  // Sync selection set to the displayed ids when the user is actively picking.
  // (FeatureView already pushes selection into the feature; this is the reverse
  // direction — useful when the user clicks "remove" on a chip.)
  return (
    <div className="space-y-1">
      <div className="flex items-center gap-1">
        <button
          type="button"
          onClick={onArmPick}
          className={`inline-flex items-center gap-1 px-2 py-1 rounded text-[11px] border
            ${pickArmed
              ? 'bg-kerf-300/15 border-kerf-300/50 text-kerf-200'
              : 'bg-ink-800 border-ink-700 text-ink-300 hover:border-ink-500'}`}
          title={pickArmed ? 'Stop picking edges' : 'Click in the viewport to pick edges'}
        >
          <Crosshair size={11} />
          <span>{pickArmed ? 'Picking…' : 'Pick edges'}</span>
        </button>
        <span className="text-[11px] text-ink-500">{ids.length} selected</span>
      </div>
      <div className="flex flex-wrap gap-1">
        {ids.map((id) => (
          <button
            key={id}
            type="button"
            onClick={() => {
              const next = ids.filter((x) => x !== id)
              onChange(next)
              // Also update the viewport selection so the highlight removes.
              const filteredEdges = new Set(
                Array.from(selection?.edgeIds || []).filter((k) => Number(k.split('|')[1]) !== id)
              )
              setSelection({ faceIds: selection?.faceIds || new Set(), edgeIds: filteredEdges })
            }}
            className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-ink-800 border border-ink-700 text-[11px] font-mono text-ink-200 hover:bg-red-900/30 hover:border-red-700"
            title={`Remove edge ${id}`}
          >
            <span>e{id}</span>
            <span className="text-ink-500">×</span>
          </button>
        ))}
      </div>
    </div>
  )
}

function FaceIdsField({ value, onChange, pickArmed, onArmPick, selection, setSelection }) {
  const ids = Array.isArray(value) ? value : []
  return (
    <div className="space-y-1">
      <div className="flex items-center gap-1">
        <button
          type="button"
          onClick={onArmPick}
          className={`inline-flex items-center gap-1 px-2 py-1 rounded text-[11px] border
            ${pickArmed
              ? 'bg-kerf-300/15 border-kerf-300/50 text-kerf-200'
              : 'bg-ink-800 border-ink-700 text-ink-300 hover:border-ink-500'}`}
          title={pickArmed ? 'Stop picking faces' : 'Click in the viewport to pick faces'}
        >
          <Crosshair size={11} />
          <span>{pickArmed ? 'Picking…' : 'Pick faces'}</span>
        </button>
        <span className="text-[11px] text-ink-500">{ids.length} selected</span>
      </div>
      <div className="flex flex-wrap gap-1">
        {ids.map((id) => (
          <button
            key={id}
            type="button"
            onClick={() => {
              const next = ids.filter((x) => x !== id)
              onChange(next)
              const filteredFaces = new Set(
                Array.from(selection?.faceIds || []).filter((k) => Number(k.split('|')[1]) !== id)
              )
              setSelection({ edgeIds: selection?.edgeIds || new Set(), faceIds: filteredFaces })
            }}
            className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-ink-800 border border-ink-700 text-[11px] font-mono text-ink-200 hover:bg-red-900/30 hover:border-red-700"
            title={`Remove face ${id}`}
          >
            <span>f{id}</span>
            <span className="text-ink-500">×</span>
          </button>
        ))}
      </div>
    </div>
  )
}

function SingleFaceIdField({ value, onChange, onArmPick }) {
  return (
    <div className="flex items-center gap-1">
      <button
        type="button"
        onClick={onArmPick}
        className="inline-flex items-center gap-1 px-2 py-1 rounded text-[11px] border bg-ink-800 border-ink-700 text-ink-300 hover:border-ink-500"
      >
        <Crosshair size={11} />
        <span>Pick face</span>
      </button>
      <input
        type="number"
        value={value ?? ''}
        onChange={(ev) => onChange(ev.target.value === '' ? '' : Number(ev.target.value))}
        className="flex-1 px-2 py-1 bg-ink-950 border border-ink-700 rounded text-xs font-mono
                   focus:outline-none focus:border-kerf-300/60"
        placeholder="face id"
      />
    </div>
  )
}

function AxisField({ value, onChange, onArmPick }) {
  // value can be 'x'|'y'|'z' (string) or a numeric edge id.
  const isEdge = typeof value === 'number'
  return (
    <div className="space-y-1">
      <div className="flex items-center gap-1">
        <select
          value={isEdge ? '_edge' : (value || 'x')}
          onChange={(ev) => {
            if (ev.target.value === '_edge') return // user must arm pick
            onChange(ev.target.value)
          }}
          className="flex-1 px-2 py-1 bg-ink-950 border border-ink-700 rounded text-xs
                     focus:outline-none focus:border-kerf-300/60"
        >
          <option value="x">X</option>
          <option value="y">Y</option>
          <option value="z">Z</option>
          <option value="_edge">{isEdge ? `Edge ${value}` : 'Pick edge…'}</option>
        </select>
        <button
          type="button"
          onClick={onArmPick}
          className="inline-flex items-center gap-1 px-2 py-1 rounded text-[11px] border bg-ink-800 border-ink-700 text-ink-300 hover:border-ink-500"
          title="Pick an edge in the viewport"
        >
          <Crosshair size={11} />
        </button>
      </div>
    </div>
  )
}

function PlaneField({ value, onChange, onArmPick }) {
  // value can be 'xy'|'xz'|'yz' (string) or a numeric face id.
  const isFace = typeof value === 'number'
  return (
    <div className="space-y-1">
      <div className="flex items-center gap-1">
        <select
          value={isFace ? '_face' : (value || 'xy')}
          onChange={(ev) => {
            if (ev.target.value === '_face') return
            onChange(ev.target.value)
          }}
          className="flex-1 px-2 py-1 bg-ink-950 border border-ink-700 rounded text-xs
                     focus:outline-none focus:border-kerf-300/60"
        >
          <option value="xy">XY</option>
          <option value="xz">XZ</option>
          <option value="yz">YZ</option>
          <option value="_face">{isFace ? `Face ${value}` : 'Pick face…'}</option>
        </select>
        <button
          type="button"
          onClick={onArmPick}
          className="inline-flex items-center gap-1 px-2 py-1 rounded text-[11px] border bg-ink-800 border-ink-700 text-ink-300 hover:border-ink-500"
          title="Pick a planar face in the viewport"
        >
          <Crosshair size={11} />
        </button>
      </div>
    </div>
  )
}

// Shared toolbar mode-button. Active state uses kerf-300 background +
// brighter text so it reads as "armed", not just "highlighted".
function ModeBtn({ active, onClick, icon: Icon, label, title }) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      className={`inline-flex items-center gap-1.5 px-2 py-1.5 rounded-md border text-[11px] transition-colors flex-shrink-0
        ${active
          ? 'border-kerf-300/60 bg-kerf-300/20 text-kerf-100 shadow-[0_0_0_1px_rgba(255,214,51,0.2)]'
          : 'border-transparent bg-transparent text-ink-300 hover:bg-ink-800 hover:text-ink-100'}`}
    >
      <Icon size={12} />
      <span>{label}</span>
    </button>
  )
}

// Helper: read an array-valued field on a feature node by id (for sketch-on-
// face and one-shot pick path). Tolerant of missing nodes.
function _arrayField(tree, featureId, fieldKey) {
  const n = tree.find((x) => x.id === featureId)
  return Array.isArray(n?.[fieldKey]) ? n[fieldKey] : []
}
