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
    from kerf_cad_core.geom.nurbs import NurbsCurve, make_line_nurbs, make_circle_nurbs
    import numpy as np

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
        pass
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
