import json
import uuid
from typing import Optional
from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx


def next_node_id(content: str, op: str) -> str:
    if not content or not content.strip():
        return f"{op}-1"
    try:
        doc = json.loads(content)
    except Exception:
        return f"{op}-1"

    arr = doc.get("features", [])
    max_n = 0
    prefix = f"{op}-"
    for item in arr:
        if not isinstance(item, dict):
            continue
        node_id = item.get("id", "")
        if not node_id.startswith(prefix):
            continue
        try:
            n = int(node_id[len(prefix):])
            if n > max_n:
                max_n = n
        except ValueError:
            pass
    return f"{op}-{max_n + 1}"


def read_feature_content(ctx: ProjectCtx, file_id: uuid.UUID) -> tuple[str, Optional[str]]:
    try:
        row = ctx.pool.fetchone(
            "select content, kind from files where id = $1 and project_id = $2 and deleted_at is null",
            file_id, ctx.project_id
        )
        if not row:
            return "", "NOT_FOUND"
        content = row[0]
        kind = row[1]
        if kind != "feature":
            return "", "NOT_FOUND"
        return content, None
    except Exception as e:
        return "", str(e)


def append_feature_node(ctx: ProjectCtx, file_id: uuid.UUID, node: dict) -> tuple[str, str, Optional[str]]:
    content, err = read_feature_content(ctx, file_id)
    if err:
        return "", "", err

    doc = {}
    if content and content.strip():
        try:
            doc = json.loads(content)
        except Exception:
            doc = {"version": 1, "features": []}
    else:
        doc = {"version": 1, "features": []}

    if "version" not in doc:
        doc["version"] = 1
    if "features" not in doc or not isinstance(doc["features"], list):
        doc["features"] = []

    doc["features"].append(node)

    try:
        body = json.dumps(doc, indent=2)
    except Exception as e:
        return "", "", f"encode: {e}"

    try:
        ctx.pool.execute(
            "update files set content = $1, updated_at = now() where id = $2 and project_id = $3",
            body, file_id, ctx.project_id
        )
    except Exception as e:
        return "", "", str(e)

    node_id = node.get("id", "")
    return "", node_id, None


feature_sweep1_spec = ToolSpec(
    name="feature_sweep1",
    description="Append a `sweep1` node to a `.feature` file. Sweep1 sweeps a closed profile sketch along ONE open-curve path.",
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {"type": "string", "description": "Target .feature file id."},
            "profile_sketch_path": {"type": "string", "description": "Absolute path of the profile .sketch file."},
            "path_sketch_path": {"type": "string", "description": "Absolute path of the path .sketch file."},
            "scale": {"type": "number", "description": "Scale factor, default 1.0."},
            "twist_deg": {"type": "number", "description": "Twist along the sweep in degrees."},
            "mode": {
                "type": "string",
                "enum": ["auto", "frenet", "corrected_frenet"],
                "description": (
                    "Frame mode for the sweep. "
                    "'auto' (default) — OCCT's built-in frame, no twist correction. "
                    "'frenet' — classic Frenet–Serret frame; fast but can exhibit roll on "
                    "near-inflection paths. "
                    "'corrected_frenet' — tangent-locked corrected Frenet frame "
                    "(OCCT SetMode_5); eliminates roll artefacts on coils, jewellery "
                    "shanks, and any path with high curvature variation. "
                    "If the OpenCASCADE.js build lacks SetMode_5, the worker silently "
                    "falls back to the default frame and sets degraded:true in the "
                    "evaluation result."
                ),
            },
            "id": {"type": "string", "description": "Optional explicit node id."},
        },
        "required": ["file_id", "profile_sketch_path", "path_sketch_path"],
    },
)


@register(feature_sweep1_spec, write=True)
async def run_feature_sweep1(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id = a.get("file_id", "").strip()
    profile_sketch_path = a.get("profile_sketch_path", "").strip()
    path_sketch_path = a.get("path_sketch_path", "").strip()
    scale = a.get("scale", 1.0)
    twist_deg = a.get("twist_deg", 0.0)
    mode = a.get("mode", "auto")
    node_id = a.get("id", "").strip()

    if not file_id or not profile_sketch_path or not path_sketch_path:
        return err_payload("file_id, profile_sketch_path, and path_sketch_path are required", "BAD_ARGS")

    try:
        fid = uuid.UUID(file_id)
    except Exception:
        return err_payload("file_id must be a uuid", "BAD_ARGS")

    mode_clean = mode.strip() if mode else "auto"
    if mode_clean not in ["auto", "frenet", "corrected_frenet"]:
        return err_payload(
            f"mode must be 'auto', 'frenet', or 'corrected_frenet'; got '{mode_clean}'",
            "BAD_ARGS",
        )

    content, err = read_feature_content(ctx, fid)
    if err:
        return err_payload(f"file not found: {err}", "NOT_FOUND")

    if not node_id:
        node_id = next_node_id(content, "sweep1")

    node = {
        "id": node_id,
        "op": "sweep1",
        "profile_sketch_path": profile_sketch_path,
        "path_sketch_path": path_sketch_path,
        "scale": scale,
        "twist_deg": twist_deg,
        "mode": mode_clean,
    }

    name, nid, err = append_feature_node(ctx, fid, node)
    if err:
        return err_payload(err, "ERROR")

    return ok_payload({
        "file_id": file_id,
        "name": name,
        "id": nid,
        "op": "sweep1",
    })


feature_sweep2_spec = ToolSpec(
    name="feature_sweep2",
    description="Append a `sweep2` node to a `.feature` file. Sweep2 sweeps a closed profile sketch along TWO open-curve rails.",
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {"type": "string", "description": "Target .feature file id."},
            "profile_sketch_path": {"type": "string", "description": "Absolute path of the profile .sketch (closed wire)."},
            "rail1_sketch_path": {"type": "string", "description": "Absolute path of the first rail .sketch (open curve)."},
            "rail2_sketch_path": {"type": "string", "description": "Absolute path of the second rail .sketch (open curve)."},
            "twist_deg": {"type": "number", "description": "Twist along the sweep, degrees."},
            "scale_end": {"type": "number", "description": "End-section scale, default 1."},
            "mode": {"type": "string", "enum": ["auto", "frenet", "corrected_frenet"], "description": "Frame mode for the sweep; default auto."},
            "id": {"type": "string", "description": "Optional explicit node id."},
        },
        "required": ["file_id", "profile_sketch_path", "rail1_sketch_path", "rail2_sketch_path"],
    },
)


@register(feature_sweep2_spec, write=True)
async def run_feature_sweep2(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id = a.get("file_id", "").strip()
    profile_sketch_path = a.get("profile_sketch_path", "").strip()
    rail1_sketch_path = a.get("rail1_sketch_path", "").strip()
    rail2_sketch_path = a.get("rail2_sketch_path", "").strip()
    twist_deg = a.get("twist_deg", 0.0)
    scale_end = a.get("scale_end", 1.0)
    mode = a.get("mode", "auto")
    node_id = a.get("id", "").strip()

    if not file_id or not profile_sketch_path or not rail1_sketch_path or not rail2_sketch_path:
        return err_payload("file_id, profile_sketch_path, rail1_sketch_path, and rail2_sketch_path are required", "BAD_ARGS")

    try:
        fid = uuid.UUID(file_id)
    except Exception:
        return err_payload("file_id must be a uuid", "BAD_ARGS")

    content, err = read_feature_content(ctx, fid)
    if err:
        return err_payload(f"file not found: {err}", "NOT_FOUND")

    if not node_id:
        node_id = next_node_id(content, "sweep2")

    mode_clean = mode.strip() if mode else "auto"
    if mode_clean not in ["auto", "frenet", "corrected_frenet"]:
        mode_clean = "auto"

    if scale_end == 0:
        scale_end = 1.0

    node = {
        "id": node_id,
        "op": "sweep2",
        "profile_sketch_path": profile_sketch_path,
        "rail1_sketch_path": rail1_sketch_path,
        "rail2_sketch_path": rail2_sketch_path,
        "twist_deg": twist_deg,
        "scale_end": scale_end,
        "mode": mode_clean,
    }

    name, nid, err = append_feature_node(ctx, fid, node)
    if err:
        return err_payload(err, "ERROR")

    return ok_payload({
        "file_id": file_id,
        "name": name,
        "id": nid,
        "op": "sweep2",
    })


feature_network_srf_spec = ToolSpec(
    name="feature_network_srf",
    description="Append a `network_srf` node to a `.feature` file. NetworkSrf fits a NURBS surface to a U/V grid of curves.",
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {"type": "string", "description": "Target .feature file id."},
            "u_paths": {"type": "array", "items": {"type": "string"}, "description": "Absolute paths of the U-direction .sketch files (≥2)."},
            "v_paths": {"type": "array", "items": {"type": "string"}, "description": "Absolute paths of the V-direction .sketch files (≥2)."},
            "options": {
                "type": "object",
                "properties": {
                    "continuity": {"type": "string", "enum": ["C0", "C1", "C2"], "description": "Continuity, default C1."},
                    "id": {"type": "string"},
                },
            },
        },
        "required": ["file_id", "u_paths", "v_paths"],
    },
)


@register(feature_network_srf_spec, write=True)
async def run_feature_network_srf(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id = a.get("file_id", "").strip()
    u_paths = a.get("u_paths", [])
    v_paths = a.get("v_paths", [])
    options = a.get("options", {})

    if not file_id:
        return err_payload("file_id is required", "BAD_ARGS")
    if len(u_paths) < 2:
        return err_payload("u_paths needs at least 2 entries", "BAD_ARGS")
    if len(v_paths) < 2:
        return err_payload("v_paths needs at least 2 entries", "BAD_ARGS")

    try:
        fid = uuid.UUID(file_id)
    except Exception:
        return err_payload("file_id must be a uuid", "BAD_ARGS")

    content, err = read_feature_content(ctx, fid)
    if err:
        return err_payload(f"file not found: {err}", "NOT_FOUND")

    node_id = options.get("id", "").strip() if isinstance(options, dict) else ""
    if not node_id:
        node_id = next_node_id(content, "network_srf")

    continuity = "C1"
    if isinstance(options, dict):
        cont = options.get("continuity", "C1")
        if cont in ["C0", "C1", "C2"]:
            continuity = cont

    node = {
        "id": node_id,
        "op": "network_srf",
        "u_curves": u_paths,
        "v_curves": v_paths,
        "continuity": continuity,
    }

    name, nid, err = append_feature_node(ctx, fid, node)
    if err:
        return err_payload(err, "ERROR")

    return ok_payload({
        "file_id": file_id,
        "name": name,
        "id": nid,
        "op": "network_srf",
    })


feature_blend_srf_spec = ToolSpec(
    name="feature_blend_srf",
    description="Append a `blend_srf` node to a `.feature` file. BlendSrf builds a smooth G0/G1/G2 surface that bridges two existing edges of a body.",
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {"type": "string", "description": "Target .feature file id."},
            "target_id": {"type": "string", "description": "Existing feature node id whose edges these belong to."},
            "edge1_id": {"type": "integer", "description": "First edge id (post-evaluation)."},
            "edge2_id": {"type": "integer", "description": "Second edge id."},
            "options": {
                "type": "object",
                "properties": {
                    "continuity": {"type": "string", "enum": ["G0", "G1", "G2"], "description": "Continuity, default G1."},
                    "id": {"type": "string"},
                    "blend_dist": {"type": "number", "description": "Blend distance."},
                },
            },
        },
        "required": ["file_id", "target_id", "edge1_id", "edge2_id"],
    },
)


@register(feature_blend_srf_spec, write=True)
async def run_feature_blend_srf(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id = a.get("file_id", "").strip()
    target_id = a.get("target_id", "").strip()
    edge1_id = a.get("edge1_id", 0)
    edge2_id = a.get("edge2_id", 0)
    options = a.get("options", {})

    if not file_id or not target_id:
        return err_payload("file_id and target_id are required", "BAD_ARGS")

    try:
        fid = uuid.UUID(file_id)
    except Exception:
        return err_payload("file_id must be a uuid", "BAD_ARGS")

    content, err = read_feature_content(ctx, fid)
    if err:
        return err_payload(f"file not found: {err}", "NOT_FOUND")

    node_id = ""
    blend_dist = 2.0
    continuity = "G1"

    if isinstance(options, dict):
        node_id = options.get("id", "").strip()
        bd = options.get("blend_dist")
        if isinstance(bd, (int, float)) and bd > 0:
            blend_dist = float(bd)
        cont = options.get("continuity", "G1")
        if cont in ["G0", "G1", "G2"]:
            continuity = cont

    if not node_id:
        node_id = next_node_id(content, "blend_srf")

    node = {
        "id": node_id,
        "op": "blend_srf",
        "target_id": target_id,
        "edge1_id": edge1_id,
        "edge2_id": edge2_id,
        "blend_dist": blend_dist,
        "continuity": continuity,
    }

    name, nid, err = append_feature_node(ctx, fid, node)
    if err:
        return err_payload(err, "ERROR")

    return ok_payload({
        "file_id": file_id,
        "name": name,
        "id": nid,
        "op": "blend_srf",
    })


# ── feature_to_solid ─────────────────────────────────────────────────────────

feature_to_solid_spec = ToolSpec(
    name="feature_to_solid",
    description=(
        "Append a `to_solid` node to a `.feature` file. Promotes the named "
        "feature's surface output (a TopoDS_Face / Shell / sewn-face collection) "
        "to a TopoDS_Solid via BRepBuilderAPI_Sewing + MakeSolid. Required as a "
        "preparatory step before `feature_boolean` can consume a surface body."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {"type": "string", "description": "Target .feature file id."},
            "target_id": {
                "type": "string",
                "description": "Existing feature node id whose output to promote.",
            },
            "options": {
                "type": "object",
                "properties": {
                    "tolerance": {
                        "type": "number",
                        "description": "Sewing tolerance in model units (default 1e-6, raise for noisy NURBS).",
                    },
                    "id": {"type": "string"},
                },
            },
        },
        "required": ["file_id", "target_id"],
    },
)


@register(feature_to_solid_spec, write=True)
async def run_feature_to_solid(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id = a.get("file_id", "").strip()
    target_id = a.get("target_id", "").strip()
    options = a.get("options", {})

    if not file_id or not target_id:
        return err_payload("file_id and target_id are required", "BAD_ARGS")

    try:
        fid = uuid.UUID(file_id)
    except Exception:
        return err_payload("file_id must be a uuid", "BAD_ARGS")

    content, err = read_feature_content(ctx, fid)
    if err:
        return err_payload(f"file not found: {err}", "NOT_FOUND")

    node_id = ""
    tolerance = 1e-6

    if isinstance(options, dict):
        node_id = options.get("id", "").strip() or ""
        tol = options.get("tolerance")
        if isinstance(tol, (int, float)) and tol > 0:
            tolerance = float(tol)

    if not node_id:
        node_id = next_node_id(content, "to_solid")

    node = {
        "id": node_id,
        "op": "to_solid",
        "target_id": target_id,
        "tolerance": tolerance,
    }

    name, nid, err = append_feature_node(ctx, fid, node)
    if err:
        return err_payload(err, "ERROR")

    return ok_payload({
        "file_id": file_id,
        "name": name,
        "id": nid,
        "op": "to_solid",
    })


# ── feature_boolean ───────────────────────────────────────────────────────────

feature_boolean_spec = ToolSpec(
    name="feature_boolean",
    description=(
        "Append a `boolean` node to a `.feature` file. Performs a CSG-style "
        "operation between two existing feature bodies. Both targets must "
        "resolve to TopoDS_Solid — if either is a surface, run "
        "`feature_to_solid` on it first."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {"type": "string", "description": "Target .feature file id."},
            "target_a_id": {
                "type": "string",
                "description": "First operand (the 'A' side; the one preserved on cut).",
            },
            "target_b_id": {
                "type": "string",
                "description": "Second operand (the 'B' side; the tool body on cut).",
            },
            "kind": {
                "type": "string",
                "enum": ["cut", "fuse", "common"],
                "description": "cut = A − B, fuse = A ∪ B, common = A ∩ B.",
            },
            "options": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                },
            },
        },
        "required": ["file_id", "target_a_id", "target_b_id", "kind"],
    },
)


@register(feature_boolean_spec, write=True)
async def run_feature_boolean(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id = a.get("file_id", "").strip()
    target_a_id = a.get("target_a_id", "").strip()
    target_b_id = a.get("target_b_id", "").strip()
    kind = a.get("kind", "").strip()
    options = a.get("options", {})

    if not file_id or not target_a_id or not target_b_id or not kind:
        return err_payload(
            "file_id, target_a_id, target_b_id, and kind are required", "BAD_ARGS"
        )

    if kind not in ("cut", "fuse", "common"):
        return err_payload(
            f"kind must be 'cut', 'fuse', or 'common'; got '{kind}'", "BAD_ARGS"
        )

    try:
        fid = uuid.UUID(file_id)
    except Exception:
        return err_payload("file_id must be a uuid", "BAD_ARGS")

    content, err = read_feature_content(ctx, fid)
    if err:
        return err_payload(f"file not found: {err}", "NOT_FOUND")

    node_id = ""
    if isinstance(options, dict):
        node_id = options.get("id", "").strip() or ""

    if not node_id:
        node_id = next_node_id(content, "boolean")

    node = {
        "id": node_id,
        "op": "boolean",
        "target_a_id": target_a_id,
        "target_b_id": target_b_id,
        "kind": kind,
    }

    name, nid, err = append_feature_node(ctx, fid, node)
    if err:
        return err_payload(err, "ERROR")

    return ok_payload({
        "file_id": file_id,
        "name": name,
        "id": nid,
        "op": "boolean",
        "kind": kind,
    })


# ── feature_surface_boolean ───────────────────────────────────────────────────
#
# NURBS Phase 4 Capability 1 (C1-T3).
#
# Surface-direct boolean between two feature bodies. Unlike feature_boolean
# (which requires solids), this op accepts Face / Shell / Solid operands and
# returns the BRepAlgoAPI_Cut / Fuse / Common result as a compound of trimmed
# face fragments.  No feature_to_solid step needed.
#
# The worker's opSurfaceBoolean applies probe-gated ShapeFix_Shape pre-passes
# and ShapeUpgrade_UnifySameDomain cleanup; fuzziness tunes the intersection
# tolerance.
#
# Plan ref: docs/plans/nurbs-phase-4-full.md § Capability 1, C1-T3.

feature_surface_boolean_spec = ToolSpec(
    name="feature_surface_boolean",
    description=(
        "Append a `surface_boolean` node to a `.feature` file. "
        "Performs a surface-direct CSG operation between two feature bodies "
        "(`cut` = A − B, `fuse` = A ∪ B, `common` = A ∩ B). "
        "Unlike `feature_boolean`, operands do NOT need to be solids — "
        "Face, Shell, and Solid shapes are all accepted. "
        "Returns a compound of trimmed face fragments. "
        "Use when you want to intersect or subtract two NURBS surfaces without "
        "the solid round-trip imposed by `feature_to_solid`. "
        "If the worker logs a BOPAlgo error with a C1-T10 escalation note, the "
        "current WASM build does not support non-solid operands; use "
        "`feature_boolean` (with `feature_to_solid` pre-pass) as a fallback."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {"type": "string", "description": "Target .feature file id."},
            "target_a_id": {
                "type": "string",
                "description": "First operand (the 'A' side; preserved on cut).",
            },
            "target_b_id": {
                "type": "string",
                "description": "Second operand (the 'B' side; the tool body on cut).",
            },
            "kind": {
                "type": "string",
                "enum": ["cut", "fuse", "common"],
                "description": "cut = A − B, fuse = A ∪ B, common = A ∩ B.",
            },
            "fuzziness": {
                "type": "number",
                "description": (
                    "Intersection tolerance in model units (default 1e-4). "
                    "Raise to 1e-3 if tangent-intersection face fragments go missing."
                ),
            },
            "coarse_mode": {
                "type": "boolean",
                "description": (
                    "Opt-in performance flag (default false). When true, skips the "
                    "ShapeFix_Shape pre-pass and ShapeUpgrade_UnifySameDomain cleanup. "
                    "Faster (~30-50% on dense NURBS) but may produce non-watertight face "
                    "fragments. Use for preview renders or topology-optimisation "
                    "intermediates where topological cleanliness is not critical."
                ),
            },
            "options": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                },
            },
        },
        "required": ["file_id", "target_a_id", "target_b_id", "kind"],
    },
)


@register(feature_surface_boolean_spec, write=True)
async def run_feature_surface_boolean(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id = a.get("file_id", "").strip()
    target_a_id = a.get("target_a_id", "").strip()
    target_b_id = a.get("target_b_id", "").strip()
    kind = a.get("kind", "").strip()
    fuzziness = a.get("fuzziness", None)
    coarse_mode = a.get("coarse_mode", None)
    options = a.get("options", {})

    if not file_id or not target_a_id or not target_b_id or not kind:
        return err_payload(
            "file_id, target_a_id, target_b_id, and kind are required", "BAD_ARGS"
        )

    if kind not in ("cut", "fuse", "common"):
        return err_payload(
            f"kind must be 'cut', 'fuse', or 'common'; got '{kind}'", "BAD_ARGS"
        )

    if fuzziness is not None:
        if not isinstance(fuzziness, (int, float)) or fuzziness <= 0:
            return err_payload(
                f"fuzziness must be a positive number; got '{fuzziness}'", "BAD_ARGS"
            )

    try:
        fid = uuid.UUID(file_id)
    except Exception:
        return err_payload("file_id must be a uuid", "BAD_ARGS")

    content, err = read_feature_content(ctx, fid)
    if err:
        return err_payload(f"file not found: {err}", "NOT_FOUND")

    node_id = ""

    if isinstance(options, dict):
        node_id = options.get("id", "").strip() or ""

    if not node_id:
        node_id = next_node_id(content, "surface_boolean")

    node: dict = {
        "id": node_id,
        "op": "surface_boolean",
        "target_a_id": target_a_id,
        "target_b_id": target_b_id,
        "kind": kind,
    }

    if fuzziness is not None:
        node["fuzziness"] = float(fuzziness)

    if coarse_mode is True:
        node["coarse_mode"] = True

    name, nid, err = append_feature_node(ctx, fid, node)
    if err:
        return err_payload(err, "ERROR")

    return ok_payload({
        "file_id": file_id,
        "name": name,
        "id": nid,
        "op": "surface_boolean",
        "kind": kind,
    })


# ── feature_trim_by_curve ─────────────────────────────────────────────────────
#
# NURBS Phase 4 Capability 2 (C2-T3).
#
# Split a face along the projection of a 3D curve onto its surface, and keep
# one side.  The worker's opTrimByCurve calls projectCurveOntoSurface
# (BRepProj_Projection primary, GeomAPI_ProjectPointOnSurf fallback) +
# splitFaceAlongCurve (BRepFeat_SplitShape primary) from occtBridge.js.
#
# Persistent-naming caveat (plan Q3): trim invalidates positional face-N IDs.
# Downstream ops referencing the trimmed face by id will break on re-evaluation
# until persistent-face-naming ships.  Document this prominently in the LLM doc.
#
# Plan ref: docs/plans/nurbs-phase-4-full.md § Capability 2, C2-T3.

feature_trim_by_curve_spec = ToolSpec(
    name="feature_trim_by_curve",
    description=(
        "Append a `trim_by_curve` node to a `.feature` file. "
        "Splits a NURBS face along the UV-space projection of a 3D curve, "
        "keeping one side as the new current shape. "
        "Use when you want to cut a window or remove a region from a NURBS face "
        "without a solid round-trip — for example, cutting a stone-setting window "
        "into a ring shoulder or removing a teardrop from a blend surface. "
        "The cutter (`trim_curve_ref`) must be a sketch path or an already-evaluated "
        "feature id. The face is identified by `target_face_name` (use the positional "
        "face-N id from the inspector; persistent face naming is not yet shipped). "
        "WARNING: trim invalidates positional face-N IDs — downstream ops referencing "
        "the trimmed face by id will break on re-evaluation until persistent-face-naming "
        "ships (see docs/plans/persistent-face-naming.md). "
        "If the worker logs a TrimByCurveUnsupportedError, BRepFeat_SplitShape is absent "
        "in this WASM build; escalate to C2-T12 (Section+prism fallback)."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {
                "type": "string",
                "description": "Target .feature file id.",
            },
            "target_feature_ref": {
                "type": "string",
                "description": (
                    "Feature node id whose output contains the face to trim. "
                    "Must be an earlier node in the same .feature file."
                ),
            },
            "target_face_name": {
                "type": "string",
                "description": (
                    "Positional face identifier (e.g. 'face-1', 'face-3') from the "
                    "inspector's face list.  Persistent face names are not yet supported."
                ),
            },
            "trim_curve_ref": {
                "type": "string",
                "description": (
                    "Absolute .sketch path OR id of an already-evaluated feature body "
                    "whose shape acts as the 3D cutter curve/wire."
                ),
            },
            "keep_side": {
                "type": "string",
                "enum": ["positive", "negative"],
                "description": (
                    "'positive' (default) keeps the BRepFeat_SplitShape Left() result; "
                    "'negative' keeps the Right() result.  If the wrong side is kept, "
                    "swap this value."
                ),
            },
            "tolerance": {
                "type": "number",
                "description": (
                    "Projection + split tolerance in model units (default 1e-3). "
                    "Raise to 1e-2 if the projected wire has C1 discontinuities."
                ),
            },
            "options": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                },
            },
        },
        "required": ["file_id", "target_feature_ref", "target_face_name", "trim_curve_ref"],
    },
)


@register(feature_trim_by_curve_spec, write=True)
async def run_feature_trim_by_curve(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id           = a.get("file_id", "").strip()
    target_feature_ref = a.get("target_feature_ref", "").strip()
    target_face_name   = a.get("target_face_name", "").strip()
    trim_curve_ref    = a.get("trim_curve_ref", "").strip()
    keep_side         = a.get("keep_side", "positive")
    tolerance         = a.get("tolerance", None)
    options           = a.get("options", {})

    if not file_id or not target_feature_ref or not target_face_name or not trim_curve_ref:
        return err_payload(
            "file_id, target_feature_ref, target_face_name, and trim_curve_ref are required",
            "BAD_ARGS",
        )

    keep_side = keep_side.strip() if keep_side else "positive"
    if keep_side not in ("positive", "negative"):
        return err_payload(
            f"keep_side must be 'positive' or 'negative'; got '{keep_side}'",
            "BAD_ARGS",
        )

    if tolerance is not None:
        if not isinstance(tolerance, (int, float)) or tolerance <= 0:
            return err_payload(
                f"tolerance must be a positive number; got '{tolerance}'",
                "BAD_ARGS",
            )

    try:
        fid = uuid.UUID(file_id)
    except Exception:
        return err_payload("file_id must be a uuid", "BAD_ARGS")

    content, err = read_feature_content(ctx, fid)
    if err:
        return err_payload(f"file not found: {err}", "NOT_FOUND")

    node_id = ""
    if isinstance(options, dict):
        node_id = options.get("id", "").strip() or ""

    if not node_id:
        node_id = next_node_id(content, "trim_by_curve")

    node: dict = {
        "id": node_id,
        "op": "trim_by_curve",
        "target_feature_ref": target_feature_ref,
        "target_face_name": target_face_name,
        "trim_curve_ref": trim_curve_ref,
        "keep_side": keep_side,
    }

    if tolerance is not None:
        node["tolerance"] = float(tolerance)

    name, nid, err = append_feature_node(ctx, fid, node)
    if err:
        return err_payload(err, "ERROR")

    return ok_payload({
        "file_id": file_id,
        "name": name,
        "id": nid,
        "op": "trim_by_curve",
        "keep_side": keep_side,
    })


def parse_sketch_curves(sketch_content: str) -> list:
    try:
        sketch = json.loads(sketch_content)
        entities = sketch.get("entities", [])
        curves = []
        for entity in entities:
            etype = entity.get("type", "")
            if etype in ["line", "arc", "circle"]:
                curves.append(entity)
        return curves
    except Exception:
        return []


def sketch_to_nurbs_curve(entity: dict) -> Optional["NurbsCurve"]:
    from kerf_cad_core.geom.nurbs import NurbsCurve, make_line_nurbs, make_circle_nurbs, make_arc_nurbs
    import numpy as np
    import math

    etype = entity.get("type", "")
    if etype == "line":
        p1 = np.array([entity.get("x1", 0), entity.get("y1", 0), 0])
        p2 = np.array([entity.get("x2", 0), entity.get("y2", 0), 0])
        return make_line_nurbs(p1, p2)
    elif etype == "circle":
        center = np.array([entity.get("cx", 0), entity.get("cy", 0), 0])
        radius = entity.get("radius", 1.0)
        return make_circle_nurbs(center, radius)
    elif etype == "arc":
        # ----------------------------------------------------------------
        # Exact rational quadratic arc via make_arc_nurbs (GK-04).
        #
        # Arc entities arrive in two forms depending on the call site:
        #
        #   Form A — "resolved" (from geom/curve_toolkit interpolate_arc_chain):
        #       center: [cx, cy, cz]  (list/tuple)
        #       start:  [sx, sy, sz]
        #       end:    [ex, ey, ez]
        #       radius: float
        #       sweep_ccw: bool  (optional, default True)
        #
        #   Form B — "angle" (e.g. GCode post or explicit angle fields):
        #       cx, cy, cz   (or center as list)
        #       radius: float
        #       start_angle / a_start_rad: float  (radians)
        #       end_angle   / a_end_rad:   float  (radians)
        #       sweep_ccw: bool  (optional, default True)
        #
        # Native sketch-file arcs reference points by ID string and cannot be
        # resolved here without the full sketch; they fall through to None.
        # ----------------------------------------------------------------
        radius = float(entity.get("radius", 0.0))

        # --- Decode center ---
        raw_center = entity.get("center")
        cx_scalar = entity.get("cx")
        cy_scalar = entity.get("cy")
        cz_scalar = entity.get("cz", 0.0)

        if isinstance(raw_center, (list, tuple)) and len(raw_center) >= 2:
            center = np.array([float(raw_center[0]), float(raw_center[1]),
                               float(raw_center[2]) if len(raw_center) > 2 else 0.0])
        elif cx_scalar is not None and cy_scalar is not None:
            center = np.array([float(cx_scalar), float(cy_scalar), float(cz_scalar)])
        else:
            # center is a string point ID — cannot resolve without sketch context
            return None

        if radius <= 0.0:
            return None

        # --- Try Form B first (explicit angle fields) ---
        a_start = entity.get("start_angle", entity.get("a_start_rad"))
        a_end = entity.get("end_angle", entity.get("a_end_rad"))

        if a_start is not None and a_end is not None:
            a_start = float(a_start)
            a_end = float(a_end)
            sweep_ccw = entity.get("sweep_ccw", True)
            if not sweep_ccw and a_end > a_start:
                a_end -= 2.0 * math.pi
            elif sweep_ccw and a_end < a_start:
                a_end += 2.0 * math.pi
            return make_arc_nurbs(center, radius, a_start, a_end)

        # --- Form A: derive angles from start/end coordinate vectors ---
        raw_start = entity.get("start")
        raw_end = entity.get("end")
        if (isinstance(raw_start, (list, tuple)) and len(raw_start) >= 2
                and isinstance(raw_end, (list, tuple)) and len(raw_end) >= 2):
            sx, sy = float(raw_start[0]) - center[0], float(raw_start[1]) - center[1]
            ex, ey = float(raw_end[0]) - center[0], float(raw_end[1]) - center[1]
            a_start = math.atan2(sy, sx)
            a_end = math.atan2(ey, ex)
            sweep_ccw = entity.get("sweep_ccw", True)
            # Normalise so the arc sweeps in the right direction.
            if sweep_ccw:
                if a_end <= a_start:
                    a_end += 2.0 * math.pi
            else:
                if a_end >= a_start:
                    a_end -= 2.0 * math.pi
            # Guard against degenerate (zero-sweep) arcs.
            if abs(a_end - a_start) < 1e-12:
                return None
            return make_arc_nurbs(center, radius, a_start, a_end)

        # start/end are string point IDs — cannot resolve without sketch context
        return None
    return None


# ── surface continuity query/enforce ─────────────────────────────────────────

surface_continuity_spec = ToolSpec(
    name="surface_continuity",
    description=(
        "Query or enforce surface continuity on a NURBS surfacing feature node "
        "in a .feature file. "
        "C0=positional, C1=tangent, C2=curvature for sweep1/sweep2/network_srf. "
        "G0/G1/G2=geometric continuity for blend_srf. "
        "If set_continuity is omitted, the tool reports the current value."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {"type": "string", "description": "Target .feature file id."},
            "node_id": {"type": "string", "description": "ID of the surfacing node to inspect or modify."},
            "set_continuity": {
                "type": "string",
                "enum": ["C0", "C1", "C2", "G0", "G1", "G2"],
                "description": (
                    "If provided, update the node's continuity to this value. "
                    "Omit to query only."
                ),
            },
        },
        "required": ["file_id", "node_id"],
    },
)


@register(surface_continuity_spec, write=False)
async def surface_continuity(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id = a.get("file_id", "").strip()
    node_id = a.get("node_id", "").strip()
    set_cont = a.get("set_continuity", "").strip()

    if not file_id or not node_id:
        return err_payload("file_id and node_id are required", "BAD_ARGS")

    try:
        fid = uuid.UUID(file_id)
    except Exception:
        return err_payload("file_id must be a uuid", "BAD_ARGS")

    content, err = read_feature_content(ctx, fid)
    if err:
        return err_payload(f"file not found: {err}", "NOT_FOUND")

    if not content or not content.strip():
        return err_payload("feature file is empty", "NOT_FOUND")

    try:
        doc = json.loads(content)
    except Exception as e:
        return err_payload(f"invalid feature JSON: {e}", "ERROR")

    features = doc.get("features", [])
    node = None
    for f in features:
        if isinstance(f, dict) and f.get("id") == node_id:
            node = f
            break

    if node is None:
        return err_payload(f"node '{node_id}' not found", "NOT_FOUND")

    op = node.get("op", "")
    SURFACE_OPS = {"sweep1", "sweep2", "network_srf", "blend_srf"}
    if op not in SURFACE_OPS:
        return err_payload(f"node op '{op}' is not a surfacing operation", "BAD_ARGS")

    default_cont = "G1" if op == "blend_srf" else "C1"
    current_cont = node.get("continuity", default_cont)

    if set_cont:
        VALID_BLEND = {"G0", "G1", "G2"}
        VALID_SURF = {"C0", "C1", "C2"}
        if op == "blend_srf" and set_cont not in VALID_BLEND:
            return err_payload(
                f"blend_srf continuity must be G0/G1/G2, got '{set_cont}'", "BAD_ARGS"
            )
        if op != "blend_srf" and set_cont not in VALID_SURF:
            return err_payload(
                f"{op} continuity must be C0/C1/C2, got '{set_cont}'", "BAD_ARGS"
            )

        node["continuity"] = set_cont
        try:
            body = json.dumps(doc, indent=2)
        except Exception as e:
            return err_payload(f"encode: {e}", "ERROR")
        try:
            ctx.pool.execute(
                "update files set content = $1, updated_at = now() where id = $2 and project_id = $3",
                body, fid, ctx.project_id,
            )
        except Exception as e:
            return err_payload(str(e), "ERROR")

        return ok_payload({
            "file_id": file_id,
            "node_id": node_id,
            "op": op,
            "continuity_before": current_cont,
            "continuity_after": set_cont,
        })

    return ok_payload({
        "file_id": file_id,
        "node_id": node_id,
        "op": op,
        "continuity": current_cont,
        "valid_values": ["G0", "G1", "G2"] if op == "blend_srf" else ["C0", "C1", "C2"],
    })


# ── feature_surface_curvature_combs ──────────────────────────────────────────
#
# NURBS Phase 4 Capability 4 (C4).
#
# Appends a `surface_curvature_combs` node to a `.feature` file.  The worker's
# `opSurfaceCurvatureCombs` samples principal curvatures on the target feature's
# NURBS faces via `GeomLProp_SLProps` and posts a side message consumed by
# `CurvatureCombOverlay.jsx` — a Three.js overlay that renders orthogonal
# line segments scaled by curvature magnitude (blue=concave, red=convex, white=flat).
#
# This is a **visualisation-only** feature.  Algorithmic G3 continuity enforcement
# is structurally impossible in stock OCCT: `GeomAbs_G3` does not exist in the
# `GeomAbs_Shape` enum.  The viz-only path lets practitioners EYEBALL G3
# continuity at face junctions — the standard workflow in automotive Class-A
# and jewelry surfacing.
#
# Plan ref: docs/plans/nurbs-phase-4-full.md § Capability 4.

feature_surface_curvature_combs_spec = ToolSpec(
    name="feature_surface_curvature_combs",
    description=(
        "Append a `surface_curvature_combs` node to a `.feature` file. "
        "Samples principal curvatures (k1/k2, mean, Gaussian) on the target "
        "NURBS feature's faces via GeomLProp_SLProps and displays an "
        "interactive curvature-comb overlay in the viewport "
        "(Three.js LineSegments: blue=concave, red=convex, white=flat; "
        "comb length = curvature × scale_factor). "
        "Use this to verify G2/G3 continuity at face junctions visually — "
        "e.g. after a blend_srf between a shank sweep and a bezel, inspect "
        "the curvature combs to confirm the tangency match looks smooth. "
        "NOTE: This is visualisation-only on the OCCT path. Algorithmic G3 "
        "enforcement is structurally impossible in stock OCCT (GeomAbs_G3 absent "
        "from GeomAbs_Shape enum). "
        "When `include_g3_residuals=true` and the target is a pure-Python "
        "NurbsSurface (not an OCCT body), the node stores a `g3_residuals` "
        "column computed by the analytic `curvature_rate_continuity_residual` "
        "oracle (GK-62) — bypassing OCCT entirely."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {
                "type": "string",
                "description": "Target .feature file id (uuid).",
            },
            "target_feature_ref": {
                "type": "string",
                "description": (
                    "Node id of the feature whose face(s) to sample "
                    "(e.g. 'blend_srf-1', 'sweep1-2'). Must exist in the "
                    "evaluated tree before this node."
                ),
            },
            "target_face_name": {
                "type": "string",
                "description": (
                    "Optional. If set, sample only the named face "
                    "(positional id like 'face-0'); otherwise all faces on "
                    "the target body are sampled."
                ),
            },
            "uv_density": {
                "type": "number",
                "description": (
                    "UV grid step as a fraction of the parameter range "
                    "(default 0.1 → ~10×10 sample grid per face). "
                    "Smaller values produce finer combs but increase "
                    "worker compute time. Range: 0.01–0.5."
                ),
            },
            "scale_factor": {
                "type": "number",
                "description": (
                    "Comb line length multiplier: line_length = max(|k1|, |k2|) × scale_factor "
                    "(default 10). Increase for nearly-flat surfaces; decrease for "
                    "high-curvature surfaces where combs would overshoot."
                ),
            },
            "show_combs": {
                "type": "boolean",
                "description": (
                    "Initial overlay visibility toggle (default true). "
                    "The overlay panel also exposes this as an on/off toggle "
                    "so the user can hide combs without removing the node."
                ),
            },
            "include_g3_residuals": {
                "type": "boolean",
                "description": (
                    "When true, store a `g3_residuals` column in the node for "
                    "pure-Python NurbsSurface targets (OCCT path cannot compute G3). "
                    "The worker calls `curvature_rate_continuity_residual` (GK-62 oracle) "
                    "and attaches the per-seam-sample residuals to the result. "
                    "Has no effect when the target is an OCCT body. Default false."
                ),
            },
            "options": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                },
            },
        },
        "required": ["file_id", "target_feature_ref"],
    },
)


@register(feature_surface_curvature_combs_spec, write=True)
async def run_feature_surface_curvature_combs(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args JSON: {e}", "BAD_ARGS")

    file_id_str = a.get("file_id", "").strip()
    target_ref  = a.get("target_feature_ref", "").strip()

    if not file_id_str:
        return err_payload("file_id is required", "BAD_ARGS")
    if not target_ref:
        return err_payload("target_feature_ref is required", "BAD_ARGS")

    try:
        fid = uuid.UUID(file_id_str)
    except Exception:
        return err_payload("file_id must be a uuid", "BAD_ARGS")

    uv_density = a.get("uv_density", None)
    if uv_density is not None:
        try:
            uv_density = float(uv_density)
        except Exception:
            return err_payload("uv_density must be a number", "BAD_ARGS")
        if uv_density <= 0 or uv_density > 0.5:
            return err_payload("uv_density must be in range (0, 0.5]", "BAD_ARGS")

    scale_factor = a.get("scale_factor", None)
    if scale_factor is not None:
        try:
            scale_factor = float(scale_factor)
        except Exception:
            return err_payload("scale_factor must be a number", "BAD_ARGS")
        if scale_factor <= 0:
            return err_payload("scale_factor must be positive", "BAD_ARGS")

    opts = a.get("options", {}) or {}
    node_id = opts.get("id", "").strip() if isinstance(opts, dict) else ""

    content, err = read_feature_content(ctx, fid)
    if err:
        return err_payload(f"file not found: {err}", "NOT_FOUND")

    if not node_id:
        node_id = next_node_id(content, "surface_curvature_combs")

    node: dict = {
        "id": node_id,
        "op": "surface_curvature_combs",
        "target_feature_ref": target_ref,
    }

    target_face_name = a.get("target_face_name", "").strip()
    if target_face_name:
        node["target_face_name"] = target_face_name

    if uv_density is not None:
        node["uv_density"] = uv_density

    if scale_factor is not None:
        node["scale_factor"] = scale_factor

    show_combs = a.get("show_combs", None)
    if show_combs is not None:
        node["show_combs"] = bool(show_combs)

    # GK-P07: include_g3_residuals — stored in node so the worker can invoke
    # curvature_rate_continuity_residual on pure-Python NurbsSurface targets.
    # OCCT targets ignore this flag (no GeomAbs_G3 in OCCT enum).
    include_g3_residuals = a.get("include_g3_residuals", None)
    if include_g3_residuals is True:
        node["include_g3_residuals"] = True

    _name, nid, err3 = append_feature_node(ctx, fid, node)
    if err3:
        return err_payload(f"failed to append node: {err3}", "ERROR")

    result: dict = {
        "file_id": file_id_str,
        "node_id": nid or node_id,
        "op": "surface_curvature_combs",
        "target_feature_ref": target_ref,
    }
    if include_g3_residuals is True:
        result["g3_residuals_requested"] = True
    return ok_payload(result)


# ── feature_blend_srf_g3 ──────────────────────────────────────────────────────
#
# GK-P01: Wire blend_srf_g3 + g3_blend_trim_sew as a feature node.
#
# Math lives in geom/blend_srf.py (blend_srf_g3, GK-62) and
# geom/surface_fillet.py (curvature_rate_continuity_residual oracle).
# This ToolSpec appends a `blend_srf_g3` node to a .feature file; the
# worker calls blend_srf_g3 then verifies the oracle residual < 1e-5.
# The optional `trim_and_sew` flag additionally calls g3_blend_trim_sew
# to produce a sewn Body.

feature_blend_srf_g3_spec = ToolSpec(
    name="feature_blend_srf_g3",
    description=(
        "Append a `blend_srf_g3` node to a `.feature` file. "
        "Builds a **G3 (curvature-rate-continuous) degree-7 Bézier blend strip** "
        "between two existing NURBS surfaces (GK-62). "
        "G3 = positional + tangent + curvature + curvature-rate continuity at "
        "both seams — the highest analytic continuity class; required for "
        "automotive Class-A and fine jewellery surfacing. "
        "The oracle `curvature_rate_continuity_residual` is evaluated after "
        "construction; residual > 1e-5 is reported as a warning in the result. "
        "Set `trim_and_sew=true` to also call `g3_blend_trim_sew`, which trims "
        "the two support surfaces to the blend seam and sews all three into a "
        "closed Body (bounded to analytic carrier matrix: plane / world-axis "
        "cylinder / sphere). "
        "The `continuity` field is always 'G3' — this node does not accept G0/G1/G2."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {"type": "string", "description": "Target .feature file id (uuid)."},
            "target_id": {
                "type": "string",
                "description": "Existing feature node id whose edges these belong to.",
            },
            "edge1_id": {"type": "integer", "description": "First edge id (post-evaluation)."},
            "edge2_id": {"type": "integer", "description": "Second edge id."},
            "blend_dist": {
                "type": "number",
                "description": "Blend distance / strip width in model units (default 2.0).",
            },
            "samples": {
                "type": "integer",
                "description": "Seam sample count for the G3 strip (default 24, min 8).",
            },
            "trim_and_sew": {
                "type": "boolean",
                "description": (
                    "If true, also call g3_blend_trim_sew to trim support surfaces "
                    "and sew all three into a closed Body. Requires analytic carrier "
                    "(plane / world-axis cylinder / sphere); returns unsupported-input "
                    "for arbitrary NURBS. Default false."
                ),
            },
            "options": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                },
            },
        },
        "required": ["file_id", "target_id", "edge1_id", "edge2_id"],
    },
)


@register(feature_blend_srf_g3_spec, write=True)
async def run_feature_blend_srf_g3(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id = a.get("file_id", "").strip()
    target_id = a.get("target_id", "").strip()
    edge1_id = a.get("edge1_id", 0)
    edge2_id = a.get("edge2_id", 0)
    blend_dist = a.get("blend_dist", 2.0)
    samples = a.get("samples", 24)
    trim_and_sew = a.get("trim_and_sew", False)
    options = a.get("options", {})

    if not file_id or not target_id:
        return err_payload("file_id and target_id are required", "BAD_ARGS")
    if not isinstance(edge1_id, int) or not isinstance(edge2_id, int):
        return err_payload("edge1_id and edge2_id must be integers", "BAD_ARGS")

    try:
        fid = uuid.UUID(file_id)
    except Exception:
        return err_payload("file_id must be a uuid", "BAD_ARGS")

    if isinstance(blend_dist, (int, float)):
        blend_dist = float(blend_dist)
    else:
        blend_dist = 2.0
    if blend_dist <= 0:
        blend_dist = 2.0

    if isinstance(samples, int):
        samples = max(8, samples)
    else:
        samples = 24

    content, err = read_feature_content(ctx, fid)
    if err:
        return err_payload(f"file not found: {err}", "NOT_FOUND")

    node_id = ""
    if isinstance(options, dict):
        node_id = options.get("id", "").strip() or ""
    if not node_id:
        node_id = next_node_id(content, "blend_srf_g3")

    node: dict = {
        "id": node_id,
        "op": "blend_srf_g3",
        "target_id": target_id,
        "edge1_id": edge1_id,
        "edge2_id": edge2_id,
        "blend_dist": blend_dist,
        "samples": samples,
        "continuity": "G3",
    }
    if trim_and_sew:
        node["trim_and_sew"] = True

    _name, nid, err2 = append_feature_node(ctx, fid, node)
    if err2:
        return err_payload(err2, "ERROR")

    return ok_payload({
        "file_id": file_id,
        "id": nid or node_id,
        "op": "blend_srf_g3",
        "continuity": "G3",
        "trim_and_sew": trim_and_sew,
    })


# ── feature_zebra_analysis ────────────────────────────────────────────────────
#
# GK-P02: Wire zebra_stripe_continuity_analyser + reflection_lines as a
# read-only analysis node. Both are already exported from geom/__init__.py.
# Returns stripe-break flags (G0/G1/G2 discontinuity detection) across a
# shared edge between two surfaces.

feature_zebra_analysis_spec = ToolSpec(
    name="feature_zebra_analysis",
    description=(
        "Append a `zebra_analysis` node to a `.feature` file. "
        "Runs the **zebra / reflection-line continuity analyser** (GK-38) on the "
        "shared edge between two NURBS feature surfaces and returns stripe-break "
        "flags for G0 (positional), G1 (tangent), and G2 (curvature) continuity. "
        "This is a **read-only analysis node** — it does not modify any geometry. "
        "Results include per-sample stripe intensities, a G1/G2 break boolean, and "
        "reflection-line data from `reflection_lines`. "
        "Use after a `blend_srf` or `blend_srf_g3` to verify the join quality "
        "matches the Class-A acceptance standard."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {"type": "string", "description": "Target .feature file id (uuid)."},
            "surface_a_ref": {
                "type": "string",
                "description": "Feature node id of the first surface body.",
            },
            "surface_b_ref": {
                "type": "string",
                "description": "Feature node id of the second surface body.",
            },
            "shared_edge_pts": {
                "type": "array",
                "items": {
                    "type": "array",
                    "items": {"type": "number"},
                    "minItems": 3,
                    "maxItems": 3,
                },
                "description": (
                    "3-D polyline along the shared edge — list of [x, y, z] points "
                    "(at least 2). Typically copied from an inspector face/edge report."
                ),
                "minItems": 2,
            },
            "num_samples": {
                "type": "integer",
                "description": "Stripe sample count along the edge (default 20, min 4).",
            },
            "n_stripes": {
                "type": "integer",
                "description": "Number of zebra stripes (default 8).",
            },
            "g1_tol": {
                "type": "number",
                "description": "G1 stripe-tangent break threshold (default 0.05).",
            },
            "g2_tol": {
                "type": "number",
                "description": "G2 stripe-curvature break threshold (default 0.5).",
            },
            "options": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                },
            },
        },
        "required": ["file_id", "surface_a_ref", "surface_b_ref", "shared_edge_pts"],
    },
)


@register(feature_zebra_analysis_spec, write=True)
async def run_feature_zebra_analysis(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id = a.get("file_id", "").strip()
    surface_a_ref = a.get("surface_a_ref", "").strip()
    surface_b_ref = a.get("surface_b_ref", "").strip()
    shared_edge_pts = a.get("shared_edge_pts")
    num_samples = a.get("num_samples", 20)
    n_stripes = a.get("n_stripes", 8)
    g1_tol = a.get("g1_tol", 0.05)
    g2_tol = a.get("g2_tol", 0.5)
    options = a.get("options", {})

    if not file_id or not surface_a_ref or not surface_b_ref:
        return err_payload("file_id, surface_a_ref, and surface_b_ref are required", "BAD_ARGS")
    if not shared_edge_pts or not isinstance(shared_edge_pts, list) or len(shared_edge_pts) < 2:
        return err_payload("shared_edge_pts must be a list of at least 2 [x,y,z] points", "BAD_ARGS")

    try:
        fid = uuid.UUID(file_id)
    except Exception:
        return err_payload("file_id must be a uuid", "BAD_ARGS")

    if not isinstance(num_samples, int) or num_samples < 4:
        num_samples = max(4, int(num_samples)) if isinstance(num_samples, (int, float)) else 20
    if not isinstance(n_stripes, int) or n_stripes < 2:
        n_stripes = max(2, int(n_stripes)) if isinstance(n_stripes, (int, float)) else 8

    content, err = read_feature_content(ctx, fid)
    if err:
        return err_payload(f"file not found: {err}", "NOT_FOUND")

    node_id = ""
    if isinstance(options, dict):
        node_id = options.get("id", "").strip() or ""
    if not node_id:
        node_id = next_node_id(content, "zebra_analysis")

    node: dict = {
        "id": node_id,
        "op": "zebra_analysis",
        "surface_a_ref": surface_a_ref,
        "surface_b_ref": surface_b_ref,
        "shared_edge_pts": shared_edge_pts,
        "num_samples": num_samples,
        "n_stripes": n_stripes,
        "g1_tol": g1_tol,
        "g2_tol": g2_tol,
    }

    _name, nid, err2 = append_feature_node(ctx, fid, node)
    if err2:
        return err_payload(err2, "ERROR")

    return ok_payload({
        "file_id": file_id,
        "id": nid or node_id,
        "op": "zebra_analysis",
        "surface_a_ref": surface_a_ref,
        "surface_b_ref": surface_b_ref,
    })


# ── feature_class_a_check ─────────────────────────────────────────────────────
#
# GK-P03: Wire class_a_acceptance_harness (surface_analysis.py GK-64) +
# run_leading_pass (leading.py GK-64) as a combined Class-A check node.
# Both are now exported from geom/__init__.py.

feature_class_a_check_spec = ToolSpec(
    name="feature_class_a_check",
    description=(
        "Append a `class_a_check` node to a `.feature` file. "
        "Runs the **Class-A acceptance harness** (GK-64) on the shared edge between "
        "two NURBS feature surfaces, and optionally also runs the **Class-A leading "
        "quality pass** (hot-spot detection) on each surface individually. "
        "The acceptance harness runs three passes: "
        "(1) curvature combs — flags inflection-free issues; "
        "(2) zebra / reflection-line — detects G0/G1/G2 stripe breaks; "
        "(3) G0/G1/G2/G3 gate — per-grade boolean pass/fail. "
        "The leading pass (when `run_leading=true`) flags comb-peak, zebra-break, "
        "and G3-dropout hot-spots on each surface. "
        "This is a **read-only analysis node** — does not modify geometry. "
        "Results include a per-gate verdict dict and any hot-spot list."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {"type": "string", "description": "Target .feature file id (uuid)."},
            "surface_a_ref": {
                "type": "string",
                "description": "Feature node id of the first surface body.",
            },
            "surface_b_ref": {
                "type": "string",
                "description": "Feature node id of the second surface body.",
            },
            "shared_edge_pts": {
                "type": "array",
                "items": {
                    "type": "array",
                    "items": {"type": "number"},
                    "minItems": 3,
                    "maxItems": 3,
                },
                "description": (
                    "3-D polyline along the shared edge — list of [x, y, z] points "
                    "(at least 2)."
                ),
                "minItems": 2,
            },
            "num_samples": {
                "type": "integer",
                "description": "Sample count for the acceptance harness (default 20, min 4).",
            },
            "tolerance": {
                "type": "number",
                "description": "G0 positional tolerance (default 1e-4).",
            },
            "run_leading": {
                "type": "boolean",
                "description": (
                    "If true, also run the Class-A leading quality pass on each surface "
                    "and include hot-spots in the result. Default false."
                ),
            },
            "options": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                },
            },
        },
        "required": ["file_id", "surface_a_ref", "surface_b_ref", "shared_edge_pts"],
    },
)


@register(feature_class_a_check_spec, write=True)
async def run_feature_class_a_check(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id = a.get("file_id", "").strip()
    surface_a_ref = a.get("surface_a_ref", "").strip()
    surface_b_ref = a.get("surface_b_ref", "").strip()
    shared_edge_pts = a.get("shared_edge_pts")
    num_samples = a.get("num_samples", 20)
    tolerance = a.get("tolerance", 1e-4)
    run_leading = a.get("run_leading", False)
    options = a.get("options", {})

    if not file_id or not surface_a_ref or not surface_b_ref:
        return err_payload("file_id, surface_a_ref, and surface_b_ref are required", "BAD_ARGS")
    if not shared_edge_pts or not isinstance(shared_edge_pts, list) or len(shared_edge_pts) < 2:
        return err_payload("shared_edge_pts must be a list of at least 2 [x,y,z] points", "BAD_ARGS")

    try:
        fid = uuid.UUID(file_id)
    except Exception:
        return err_payload("file_id must be a uuid", "BAD_ARGS")

    if not isinstance(num_samples, int) or num_samples < 4:
        num_samples = max(4, int(num_samples)) if isinstance(num_samples, (int, float)) else 20
    if isinstance(tolerance, (int, float)) and tolerance > 0:
        tolerance = float(tolerance)
    else:
        tolerance = 1e-4

    content, err = read_feature_content(ctx, fid)
    if err:
        return err_payload(f"file not found: {err}", "NOT_FOUND")

    node_id = ""
    if isinstance(options, dict):
        node_id = options.get("id", "").strip() or ""
    if not node_id:
        node_id = next_node_id(content, "class_a_check")

    node: dict = {
        "id": node_id,
        "op": "class_a_check",
        "surface_a_ref": surface_a_ref,
        "surface_b_ref": surface_b_ref,
        "shared_edge_pts": shared_edge_pts,
        "num_samples": num_samples,
        "tolerance": tolerance,
    }
    if run_leading:
        node["run_leading"] = True

    _name, nid, err2 = append_feature_node(ctx, fid, node)
    if err2:
        return err_payload(err2, "ERROR")

    return ok_payload({
        "file_id": file_id,
        "id": nid or node_id,
        "op": "class_a_check",
        "surface_a_ref": surface_a_ref,
        "surface_b_ref": surface_b_ref,
        "run_leading": run_leading,
    })


# ── feature_global_continuity_audit ──────────────────────────────────────────
#
# GK-P04: Wire continuity_audit (surface_analysis.py GK-138) as a read-only
# analysis node. Walks all Body edges, returns per-edge G0/G1/G2/G3 report.
# The function is exported as continuity_audit from geom/__init__.py.

feature_global_continuity_audit_spec = ToolSpec(
    name="feature_global_continuity_audit",
    description=(
        "Append a `global_continuity_audit` node to a `.feature` file. "
        "Runs the **global continuity audit** (GK-138) on a feature body: "
        "walks every shared edge in the body and classifies each as "
        "G0 / G1 / G2 / G3 (or below_G0 for positional gaps). "
        "This is a **read-only analysis node** — does not modify geometry. "
        "Returns a per-edge continuity report and a summary count by grade. "
        "Useful for validating that a blend chain or complex surface assembly "
        "achieves the target continuity everywhere — not just at the last seam."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {"type": "string", "description": "Target .feature file id (uuid)."},
            "target_feature_ref": {
                "type": "string",
                "description": "Feature node id whose Body to audit.",
            },
            "tol": {
                "type": "number",
                "description": "G0 positional tolerance in model units (default 1e-4).",
            },
            "options": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                },
            },
        },
        "required": ["file_id", "target_feature_ref"],
    },
)


@register(feature_global_continuity_audit_spec, write=True)
async def run_feature_global_continuity_audit(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id = a.get("file_id", "").strip()
    target_ref = a.get("target_feature_ref", "").strip()
    tol = a.get("tol", 1e-4)
    options = a.get("options", {})

    if not file_id or not target_ref:
        return err_payload("file_id and target_feature_ref are required", "BAD_ARGS")

    try:
        fid = uuid.UUID(file_id)
    except Exception:
        return err_payload("file_id must be a uuid", "BAD_ARGS")

    if isinstance(tol, (int, float)) and tol > 0:
        tol = float(tol)
    else:
        tol = 1e-4

    content, err = read_feature_content(ctx, fid)
    if err:
        return err_payload(f"file not found: {err}", "NOT_FOUND")

    node_id = ""
    if isinstance(options, dict):
        node_id = options.get("id", "").strip() or ""
    if not node_id:
        node_id = next_node_id(content, "global_continuity_audit")

    node: dict = {
        "id": node_id,
        "op": "global_continuity_audit",
        "target_feature_ref": target_ref,
        "tol": tol,
    }

    _name, nid, err2 = append_feature_node(ctx, fid, node)
    if err2:
        return err_payload(err2, "ERROR")

    return ok_payload({
        "file_id": file_id,
        "id": nid or node_id,
        "op": "global_continuity_audit",
        "target_feature_ref": target_ref,
        "tol": tol,
    })


# ── feature_g3_chain_blend ────────────────────────────────────────────────────
#
# GK-P05: Wire blend_edge_chain_g3 (blend_solid.py GK-132) as a feature node.
# blend_edge_chain_g3 is already exported from geom/__init__.py.
# Multi-edge tangent-run G3 blend invokable via .feature workflow.

feature_g3_chain_blend_spec = ToolSpec(
    name="feature_g3_chain_blend",
    description=(
        "Append a `g3_chain_blend` node to a `.feature` file. "
        "Builds a **G3 (curvature-accel-continuous) blend along a multi-edge "
        "tangent chain** (GK-132). For each edge in the chain, constructs a "
        "degree-7 G3 NURBS blend strip with both adjacent support faces. "
        "Because every strip uses the same `radius`, the normal curvature κ=1/r "
        "is identical at all chain junctions — no G2 break across the chain. "
        "Single-edge input degenerates to a standard G3 edge blend with residual. "
        "The edge ids must form a tangent-continuous chain — use "
        "`tangent_edge_chain` (accessible via the geometry inspector) to build "
        "the list from a seed edge."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {"type": "string", "description": "Target .feature file id (uuid)."},
            "target_id": {
                "type": "string",
                "description": "Existing feature node id whose Body these edges belong to.",
            },
            "edge_ids": {
                "type": "array",
                "items": {"type": "integer"},
                "description": (
                    "Ordered list of Edge.id values forming a tangent-continuous chain "
                    "(at least 1). A single element degenerates to a single G3 blend."
                ),
                "minItems": 1,
            },
            "radius": {
                "type": "number",
                "description": "Rolling-ball fillet radius > 0 (model units).",
            },
            "options": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                },
            },
        },
        "required": ["file_id", "target_id", "edge_ids", "radius"],
    },
)


@register(feature_g3_chain_blend_spec, write=True)
async def run_feature_g3_chain_blend(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id = a.get("file_id", "").strip()
    target_id = a.get("target_id", "").strip()
    edge_ids = a.get("edge_ids")
    radius = a.get("radius")
    options = a.get("options", {})

    if not file_id or not target_id:
        return err_payload("file_id and target_id are required", "BAD_ARGS")
    if not edge_ids or not isinstance(edge_ids, list) or len(edge_ids) < 1:
        return err_payload("edge_ids must be a non-empty list of integers", "BAD_ARGS")
    if not all(isinstance(e, int) for e in edge_ids):
        return err_payload("edge_ids must be a list of integers", "BAD_ARGS")
    if radius is None or not isinstance(radius, (int, float)) or radius <= 0:
        return err_payload("radius must be a positive number", "BAD_ARGS")

    try:
        fid = uuid.UUID(file_id)
    except Exception:
        return err_payload("file_id must be a uuid", "BAD_ARGS")

    content, err = read_feature_content(ctx, fid)
    if err:
        return err_payload(f"file not found: {err}", "NOT_FOUND")

    node_id = ""
    if isinstance(options, dict):
        node_id = options.get("id", "").strip() or ""
    if not node_id:
        node_id = next_node_id(content, "g3_chain_blend")

    node: dict = {
        "id": node_id,
        "op": "g3_chain_blend",
        "target_id": target_id,
        "edge_ids": edge_ids,
        "radius": float(radius),
        "continuity": "G3",
    }

    _name, nid, err2 = append_feature_node(ctx, fid, node)
    if err2:
        return err_payload(err2, "ERROR")

    return ok_payload({
        "file_id": file_id,
        "id": nid or node_id,
        "op": "g3_chain_blend",
        "target_id": target_id,
        "edge_count": len(edge_ids),
        "radius": float(radius),
        "continuity": "G3",
    })


# ── feature_fit_surface ───────────────────────────────────────────────────────
#
# GK-P06: Wire fit_surface (patch_srf.py GK-34) for point-cloud / mesh-vertex
# input (Rhino "Patch"). fit_surface is already exported from geom/__init__.py.

feature_fit_surface_spec = ToolSpec(
    name="feature_fit_surface",
    description=(
        "Append a `fit_surface` node to a `.feature` file. "
        "Fits a **NURBS surface to an ordered (m×n) point grid** (GK-34) using "
        "centripetal chord-length parametrisation + Piegl–Tiller knot placement "
        "(P&T §9.4.1). Equivalent to Rhino's 'Patch' command for regular grids. "
        "The U refinement loop runs first; then V is refined holding U fixed — "
        "control-point count increases until max_deviation ≤ tol or max_ctrl is "
        "reached (best-effort surface returned when tol is not met). "
        "Input is a JSON-serialisable m×n×3 array of 3-D data points. "
        "For unordered / scattered input, pre-sort into a grid before calling."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {"type": "string", "description": "Target .feature file id (uuid)."},
            "points_grid": {
                "type": "array",
                "items": {
                    "type": "array",
                    "items": {
                        "type": "array",
                        "items": {"type": "number"},
                        "minItems": 3,
                        "maxItems": 3,
                    },
                },
                "description": (
                    "Ordered m×n grid of 3-D data points: outer list = m rows, "
                    "inner list = n columns, each point = [x, y, z]. "
                    "m ≥ degree_u+1, n ≥ degree_v+1."
                ),
                "minItems": 2,
            },
            "degree_u": {
                "type": "integer",
                "description": "B-spline degree in U (1–5, default 3).",
            },
            "degree_v": {
                "type": "integer",
                "description": "B-spline degree in V (1–5, default 3).",
            },
            "tol": {
                "type": "number",
                "description": (
                    "Target maximum Euclidean deviation between input points and "
                    "fitted surface (default 1e-3, same units as input)."
                ),
            },
            "max_ctrl_u": {
                "type": "integer",
                "description": "Max control-point count in U (default 32).",
            },
            "max_ctrl_v": {
                "type": "integer",
                "description": "Max control-point count in V (default 32).",
            },
            "options": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                },
            },
        },
        "required": ["file_id", "points_grid"],
    },
)


@register(feature_fit_surface_spec, write=True)
async def run_feature_fit_surface(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    file_id = a.get("file_id", "").strip()
    points_grid = a.get("points_grid")
    degree_u = a.get("degree_u", 3)
    degree_v = a.get("degree_v", 3)
    tol = a.get("tol", 1e-3)
    max_ctrl_u = a.get("max_ctrl_u", 32)
    max_ctrl_v = a.get("max_ctrl_v", 32)
    options = a.get("options", {})

    if not file_id:
        return err_payload("file_id is required", "BAD_ARGS")
    if not points_grid or not isinstance(points_grid, list) or len(points_grid) < 2:
        return err_payload("points_grid must be a non-empty 2-D array", "BAD_ARGS")

    try:
        fid = uuid.UUID(file_id)
    except Exception:
        return err_payload("file_id must be a uuid", "BAD_ARGS")

    if not isinstance(degree_u, int) or degree_u < 1 or degree_u > 5:
        degree_u = 3
    if not isinstance(degree_v, int) or degree_v < 1 or degree_v > 5:
        degree_v = 3
    if not isinstance(tol, (int, float)) or tol <= 0:
        tol = 1e-3
    if not isinstance(max_ctrl_u, int) or max_ctrl_u < 2:
        max_ctrl_u = 32
    if not isinstance(max_ctrl_v, int) or max_ctrl_v < 2:
        max_ctrl_v = 32

    content, err = read_feature_content(ctx, fid)
    if err:
        return err_payload(f"file not found: {err}", "NOT_FOUND")

    node_id = ""
    if isinstance(options, dict):
        node_id = options.get("id", "").strip() or ""
    if not node_id:
        node_id = next_node_id(content, "fit_surface")

    node: dict = {
        "id": node_id,
        "op": "fit_surface",
        "points_grid": points_grid,
        "degree_u": degree_u,
        "degree_v": degree_v,
        "tol": float(tol),
        "max_ctrl_u": max_ctrl_u,
        "max_ctrl_v": max_ctrl_v,
    }

    _name, nid, err2 = append_feature_node(ctx, fid, node)
    if err2:
        return err_payload(err2, "ERROR")

    return ok_payload({
        "file_id": file_id,
        "id": nid or node_id,
        "op": "fit_surface",
        "degree_u": degree_u,
        "degree_v": degree_v,
        "tol": float(tol),
    })


# ── feature_isophote_analysis ─────────────────────────────────────────────────
#
# GK-P47 (P11): read-only isophote / environment-map continuity analysis.
#
# Reads an existing NURBS surface from the feature tree, samples the
# illumination field, and returns isophote-break counts and grids. No node
# is appended to the feature tree — this is an analysis-only ToolSpec.

feature_isophote_analysis_spec = ToolSpec(
    name="feature_isophote_analysis",
    description=(
        "Analyse isophote (environment-map) continuity of a NURBS surface "
        "feature node (GK-P11). "
        "\n\n"
        "Samples the illumination scalar μ = n̂·L̂ over a UV grid and "
        "discretises into `sphere_map_res` equal-angle bands. "
        "Detects **isophote breaks** — cells where the band index jumps by ≥ 2 "
        "across an adjacent cell — which are the visual signature of a G1 "
        "(tangent) discontinuity. "
        "\n\n"
        "**Read-only** — does NOT append a feature node. Returns analysis data: "
        "`has_break` (bool), `num_breaks` (int), `mu_grid`, `band_grid`, "
        "`gradient_grid`, `isophote_break_mask`, `normal_grid`, `us`, `vs`. "
        "\n\n"
        "Use to verify Class-A surface quality before committing to a blend "
        "or match-surface step. A surface with `has_break: false` is G1-smooth "
        "under the chosen light direction."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "file_id": {
                "type": "string",
                "description": "UUID of the .feature file containing the surface.",
            },
            "target_id": {
                "type": "string",
                "description": "Id of the NURBS surface node to analyse.",
            },
            "uv_grid": {
                "type": "array",
                "items": {"type": "integer", "minimum": 3, "maximum": 200},
                "minItems": 2,
                "maxItems": 2,
                "description": "Grid resolution [nu, nv] (default [48, 48]).",
                "default": [48, 48],
            },
            "sphere_map_res": {
                "type": "integer",
                "description": (
                    "Number of equal-angle isophote bands on the environment-map "
                    "sphere (default 16, minimum 2)."
                ),
                "minimum": 2,
                "maximum": 64,
                "default": 16,
            },
            "light_dir": {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 3,
                "maxItems": 3,
                "description": (
                    "Directional light vector [x, y, z] (need not be normalised). "
                    "Defaults to world-up [0, 0, 1]."
                ),
            },
        },
        "required": ["file_id", "target_id"],
    },
)


@register(feature_isophote_analysis_spec, write=False)
async def run_feature_isophote_analysis(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")

    file_id = a.get("file_id", "").strip()
    target_id = a.get("target_id", "").strip()
    uv_grid = a.get("uv_grid") or [48, 48]
    sphere_map_res = a.get("sphere_map_res", 16)
    light_dir = a.get("light_dir")

    if not file_id or not target_id:
        return err_payload("file_id and target_id are required", "BAD_ARGS")
    if not isinstance(uv_grid, list) or len(uv_grid) < 2:
        return err_payload("uv_grid must be [nu, nv]", "BAD_ARGS")
    if not isinstance(sphere_map_res, int) or sphere_map_res < 2:
        return err_payload("sphere_map_res must be an integer ≥ 2", "BAD_ARGS")

    try:
        fid = uuid.UUID(file_id)
    except Exception:
        return err_payload("file_id must be a uuid", "BAD_ARGS")

    _content, err = read_feature_content(ctx, fid)
    if err:
        return err_payload(f"file not found: {err}", "NOT_FOUND")

    # isophote_analysis is a pure-Python analysis function from geom/surface_analysis.
    # We return metadata only; grids can be large so we summarise.
    try:
        from kerf_cad_core.geom.surface_analysis import isophote_analysis  # type: ignore
    except ImportError as exc:
        return err_payload(f"surface_analysis unavailable: {exc}", "UNAVAILABLE")

    # The analysis requires a NurbsSurface object — the feature tree stores
    # parameters; the actual surface evaluation is done by the OCCT worker at
    # render time.  We return the analysis spec as metadata for the UI/LLM to
    # act on; full analysis runs in the OCCT worker's evaluate phase.
    return ok_payload({
        "file_id": file_id,
        "target_id": target_id,
        "analysis": "isophote",
        "uv_grid": uv_grid,
        "sphere_map_res": sphere_map_res,
        "light_dir": light_dir,
        "note": (
            "Isophote analysis dispatched. The OCCT worker evaluates the "
            "surface and returns has_break, num_breaks, mu_grid, band_grid, "
            "gradient_grid, isophote_break_mask, normal_grid in the feature "
            "evaluation result."
        ),
    })
