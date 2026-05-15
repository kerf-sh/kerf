"""
kerf-cad-core: weldment / structural-frame generator.

Three LLM tools:
  T-1  weldment_frame          skeleton + profile → member list + cut list
  T-2  weldment_profile_lookup profile designation → area / mass-per-m data
  T-3  weldment_cutlist        member list → rolled-up cut list with total mass

Design
------
Input skeleton is a list of 3-D line segments (edges) represented as
``{"start": [x, y, z], "end": [x, y, z]}``.  Each edge becomes one member
after its ends are trimmed for joint treatment.

Joint treatment rules (deterministic, documented here):
    MITER  — two members share a vertex AND lie in a common plane
             (their direction vectors are coplanar with the shared vertex).
             Each member is trimmed by half the profile's effective half-
             dimension so the cut faces meet at 45° (or at the bisector
             angle for non-90° frames).  The trim amount applied to each
             member end is:
                 trim = (effective_half / sin(θ/2))   — where θ is the
             interior angle between the two members.  For orthogonal joints
             the bisector is 45° so trim = effective_half / sin(45°).
             ``effective_half`` is approximated as sqrt(area_mm2) / 2 for
             the given profile.

    BUTT   — all other joints (T-joints, X-joints, more than two members
             meeting at a vertex, or non-coplanar members).  One member
             "passes through" and the other(s) are cut square at the face.
             The butting member is trimmed by effective_half on the end
             that meets the pass-through member.  The pass-through member
             is not trimmed at that vertex.

Vertex sharing: two edges share a vertex when their endpoints coincide
within TOLERANCE_MM (default 1e-6 mm).

Output per member (member dict):
    member_id     : int (1-based)
    edge_index    : int (0-based index into input skeleton)
    profile       : str  designation
    length_mm     : float (after end trims)
    raw_length_mm : float (straight Euclidean distance, before trimming)
    trim_start_mm : float (material removed at start vertex)
    trim_end_mm   : float (material removed at end vertex)
    start_joint   : "miter" | "butt" | "free"
    end_joint     : "miter" | "butt" | "free"
    unit_vector   : [x, y, z]  (direction from start to end, after trim)

Cut list (per profile, sorted by length):
    designation   : str
    pieces        : list of {length_mm, quantity}
    total_length_mm  : float
    total_mass_kg    : float

Units: mm, kg.  Deterministic: same input always yields same output.

Author: imranparuk
"""

from __future__ import annotations

import json
import math
from typing import Optional

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_core.utils.context import ProjectCtx

from kerf_cad_core.weldment_profiles import lookup_profile

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TOLERANCE_MM = 1e-6  # vertex-coincidence tolerance


# ---------------------------------------------------------------------------
# Pure geometry helpers (no OCC)
# ---------------------------------------------------------------------------

def _vec3(a: list[float], b: list[float]) -> list[float]:
    """Vector from a → b."""
    return [b[0] - a[0], b[1] - a[1], b[2] - a[2]]


def _length3(v: list[float]) -> float:
    return math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2)


def _norm3(v: list[float]) -> list[float]:
    """Normalise; returns zero-vector unchanged."""
    L = _length3(v)
    if L < TOLERANCE_MM:
        return [0.0, 0.0, 0.0]
    return [v[0] / L, v[1] / L, v[2] / L]


def _dot3(a: list[float], b: list[float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross3(a: list[float], b: list[float]) -> list[float]:
    return [
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    ]


def _pts_coincide(p: list[float], q: list[float]) -> bool:
    return _length3([p[0] - q[0], p[1] - q[1], p[2] - q[2]]) < TOLERANCE_MM


def _are_coplanar(d1: list[float], d2: list[float]) -> bool:
    """
    Two direction vectors are coplanar if their cross product is non-zero
    (they define a plane).  This is always true for any two non-parallel,
    non-antiparallel vectors in 3-D; the meaningful check here is whether
    the two members share a plane containing the vertex — which they always
    do for any two lines meeting at a point.  We therefore consider all
    2-member joints coplanar (true for any meeting lines in 3-D space) and
    use the "collinear" special case to guard against zero-angle joins.
    """
    cross = _cross3(d1, d2)
    return _length3(cross) > TOLERANCE_MM  # not parallel / anti-parallel


def _angle_between(d1: list[float], d2: list[float]) -> float:
    """Angle in radians between two unit vectors, in [0, π]."""
    c = max(-1.0, min(1.0, _dot3(d1, d2)))
    return math.acos(c)


def _effective_half(area_mm2: float) -> float:
    """Approximate half-dimension of the profile from its area."""
    return math.sqrt(area_mm2) / 2.0


# ---------------------------------------------------------------------------
# Core computation
# ---------------------------------------------------------------------------

def _parse_point(raw) -> Optional[list[float]]:
    """Parse a raw point (list/tuple of 3 numbers) → [x, y, z] floats."""
    try:
        pts = list(raw)
        if len(pts) != 3:
            return None
        return [float(pts[0]), float(pts[1]), float(pts[2])]
    except (TypeError, ValueError):
        return None


def _parse_edge(raw) -> Optional[tuple[list[float], list[float]]]:
    """Parse one edge dict → (start, end) or None."""
    if not isinstance(raw, dict):
        return None
    s = _parse_point(raw.get("start", []))
    e = _parse_point(raw.get("end", []))
    if s is None or e is None:
        return None
    return s, e


def _validate_skeleton(skeleton: list) -> tuple[list, list[str]]:
    """
    Validate the skeleton list.

    Returns
    -------
    (edges, errors)
        edges  — list of (start, end) tuples for valid non-degenerate edges
        errors — list of error strings (empty if all OK)
    """
    errors: list[str] = []
    edges: list[tuple[list[float], list[float]]] = []

    if not skeleton:
        errors.append("skeleton must be a non-empty list of edges")
        return edges, errors

    for i, raw in enumerate(skeleton):
        parsed = _parse_edge(raw)
        if parsed is None:
            errors.append(
                f"edge[{i}]: must be {{\"start\":[x,y,z], \"end\":[x,y,z]}}"
            )
            continue
        s, e = parsed
        if _pts_coincide(s, e):
            errors.append(f"edge[{i}]: zero-length edge (start == end)")
            continue
        edges.append((s, e))

    return edges, errors


def compute_members(
    skeleton: list,
    profile_data: dict,
    alignment: str = "centroid",
    gap_mm: float = 0.0,
) -> tuple[list[dict], list[str]]:
    """
    Compute weldment members from a skeleton + profile.

    Parameters
    ----------
    skeleton:
        List of edge dicts.
    profile_data:
        Profile dict from ``lookup_profile``.
    alignment:
        ``"centroid"`` or ``"corner"`` — centroid justification is the default;
        corner alignment shifts the profile to one corner of the section.
        Currently recorded on the output but does not change trim geometry
        (a full sweep/alignment model requires OCC).
    gap_mm:
        Extra gap (clearance) applied at each end beyond the joint trim (mm).

    Returns
    -------
    (members, errors)
    """
    edges, errors = _validate_skeleton(skeleton)
    if errors:
        return [], errors

    n = len(edges)
    area_mm2 = profile_data["area_mm2"]
    eff_half = _effective_half(area_mm2)

    # Build direction vectors (unit) per edge
    dirs: list[list[float]] = []
    for s, e in edges:
        dirs.append(_norm3(_vec3(s, e)))

    # For each edge collect which other edges share each vertex, and the
    # role of that shared vertex (start or end of this edge).
    # vertices are the 2n endpoints; group by coincidence.

    # Represent each endpoint as (edge_index, "start"|"end")
    endpoints: list[tuple[int, str]] = []
    pts: list[list[float]] = []
    for i, (s, e) in enumerate(edges):
        endpoints.append((i, "start"))
        pts.append(s)
        endpoints.append((i, "end"))
        pts.append(e)

    # Build vertex groups: list of lists of endpoint indices
    n_pts = len(pts)
    assigned = [False] * n_pts
    vertex_groups: list[list[int]] = []
    for i in range(n_pts):
        if assigned[i]:
            continue
        group = [i]
        assigned[i] = True
        for j in range(i + 1, n_pts):
            if not assigned[j] and _pts_coincide(pts[i], pts[j]):
                group.append(j)
                assigned[j] = True
        vertex_groups.append(group)

    # For each edge end, compute trim_mm and joint_type.
    # trim[edge_idx]["start" or "end"] = (trim_mm, joint_type)
    trims: dict[int, dict[str, tuple[float, str]]] = {
        i: {"start": (gap_mm, "free"), "end": (gap_mm, "free")}
        for i in range(n)
    }

    for group in vertex_groups:
        if len(group) < 2:
            # Free end — only gap applies
            continue

        # Gather distinct edges and their ends at this vertex
        meeting: list[tuple[int, str]] = [endpoints[ep_idx] for ep_idx in group]

        # Directions pointing AWAY from the shared vertex for each meeting end
        # (i.e. from the vertex into the member body)
        away_dirs: list[list[float]] = []
        for edge_idx, end in meeting:
            d = dirs[edge_idx]
            if end == "start":
                away_dirs.append(d)          # member goes start→end, away is d
            else:
                away_dirs.append([-d[0], -d[1], -d[2]])  # member goes toward end

        if len(meeting) == 2:
            # Two members meet: check for miter or butt
            d0 = away_dirs[0]
            d1 = away_dirs[1]

            if not _are_coplanar(d0, d1):
                # Parallel / anti-parallel (collinear members) — butt
                joint_type = "butt"
                # Collinear: one butts against the other
                # Pass-through (index 0) not trimmed, index 1 gets 2×eff_half
                ei0, end0 = meeting[0]
                ei1, end1 = meeting[1]
                trims[ei0][end0] = (gap_mm, "butt")
                trims[ei1][end1] = (eff_half * 2.0 + gap_mm, "butt")
            else:
                # Miter: compute bisector trim
                theta = _angle_between(d0, d1)  # angle between away-dirs
                # The interior angle between the members as drawn is π - θ
                # Trim on each member = eff_half / tan(θ/2)
                # Guard against θ ≈ 0 (collinear into same direction, degenerate)
                # or θ ≈ π (anti-parallel — back-to-back, miter at 90° face)
                sin_half = math.sin(theta / 2.0)
                if sin_half < 1e-9:
                    # Effectively parallel going same direction — no trim
                    trim_each = gap_mm
                    jtype = "butt"
                else:
                    trim_each = eff_half / sin_half + gap_mm
                    jtype = "miter"

                for (edge_idx, end) in meeting:
                    trims[edge_idx][end] = (trim_each, jtype)
        else:
            # Three or more members at one vertex: butt joint for all
            # The "primary" (longest member at this vertex, by full length) passes
            # through; others butt against it.
            # Determine pass-through: longest raw edge among those meeting here
            raw_lengths = []
            for edge_idx, end in meeting:
                s, e = edges[edge_idx]
                raw_lengths.append(_length3(_vec3(s, e)))

            max_idx = raw_lengths.index(max(raw_lengths))
            for k, (edge_idx, end) in enumerate(meeting):
                if k == max_idx:
                    trims[edge_idx][end] = (gap_mm, "butt")
                else:
                    trims[edge_idx][end] = (eff_half * 2.0 + gap_mm, "butt")

    # Build member list
    members: list[dict] = []
    for i, (s, e) in enumerate(edges):
        raw_len = _length3(_vec3(s, e))
        trim_start, jtype_start = trims[i]["start"]
        trim_end,   jtype_end   = trims[i]["end"]

        trimmed_len = raw_len - trim_start - trim_end
        # Clamp to 0 — shouldn't happen with valid geometry but be safe
        if trimmed_len < 0.0:
            trimmed_len = 0.0

        members.append({
            "member_id": i + 1,
            "edge_index": i,
            "profile": profile_data["designation"],
            "alignment": alignment,
            "length_mm": round(trimmed_len, 6),
            "raw_length_mm": round(raw_len, 6),
            "trim_start_mm": round(trim_start, 6),
            "trim_end_mm": round(trim_end, 6),
            "start_joint": jtype_start,
            "end_joint": jtype_end,
            "unit_vector": [round(v, 9) for v in dirs[i]],
        })

    return members, []


def compute_cutlist(members: list[dict], profile_data: dict) -> dict:
    """
    Roll up a member list into a cut list for a single profile.

    Returns
    -------
    dict with keys:
        designation, family, mass_per_m_kg,
        pieces          — sorted list of {length_mm, quantity},
        total_length_mm,
        total_mass_kg
    """
    mass_per_m = profile_data["mass_per_m_kg"]
    designation = profile_data["designation"]
    family = profile_data["family"]

    length_counts: dict[float, int] = {}
    total_length = 0.0
    for m in members:
        L = m["length_mm"]
        length_counts[L] = length_counts.get(L, 0) + 1
        total_length += L

    pieces = sorted(
        [{"length_mm": L, "quantity": q} for L, q in length_counts.items()],
        key=lambda x: x["length_mm"],
        reverse=True,
    )
    total_mass = (total_length / 1000.0) * mass_per_m  # mm → m

    return {
        "designation": designation,
        "family": family,
        "mass_per_m_kg": mass_per_m,
        "pieces": pieces,
        "total_length_mm": round(total_length, 6),
        "total_mass_kg": round(total_mass, 6),
    }


def compute_multi_cutlist(members: list[dict], profiles: dict[str, dict]) -> list[dict]:
    """
    Roll up a multi-profile member list grouped by designation.

    Parameters
    ----------
    members:
        Members as produced by ``compute_members`` (mixed profiles allowed).
    profiles:
        Mapping of designation → profile_data dict (pre-looked-up).

    Returns
    -------
    List of cut-list dicts, one per designation, sorted by designation.
    """
    from collections import defaultdict
    by_profile: dict[str, list[dict]] = defaultdict(list)
    for m in members:
        by_profile[m["profile"]].append(m)

    result = []
    for desig in sorted(by_profile.keys()):
        pd = profiles[desig]
        result.append(compute_cutlist(by_profile[desig], pd))
    return result


# ---------------------------------------------------------------------------
# T-1: weldment_frame
# ---------------------------------------------------------------------------

_weldment_frame_spec = ToolSpec(
    name="weldment_frame",
    description=(
        "Generate a structural weldment frame from a skeleton of 3-D line "
        "segments and a structural profile designation. "
        "Each skeleton edge becomes one member; member lengths are computed "
        "after joint trimming (miter for two-member coplanar joints, butt "
        "for T/X/multi-member joints). "
        "Returns: members (list of member dicts with trimmed length, joint "
        "type, orientation) and cutlist (rolled up by profile: pieces, "
        "total length, total mass). "
        "Pure parametric — no OCCT required; the returned ref-list is "
        "consumed by the downstream geometry worker. "
        "Units: mm for lengths, kg for mass. "
        "Profile catalogue: use weldment_profile_lookup to browse available "
        "designations (SQ, RHS, CHS, ANGLE, CHANNEL, IBEAM families). "
        "Validation: degenerate (zero-length) edges and unknown profiles "
        "return {ok:false, errors:[...]} without raising."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "skeleton": {
                "type": "array",
                "description": (
                    "List of 3-D line segments. Each element: "
                    "{\"start\":[x,y,z], \"end\":[x,y,z]} in mm."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "start": {"type": "array", "items": {"type": "number"}},
                        "end":   {"type": "array", "items": {"type": "number"}},
                    },
                    "required": ["start", "end"],
                },
            },
            "profile": {
                "type": "string",
                "description": (
                    "Structural profile designation from the catalog, e.g. "
                    "\"SQ-50x50x3\", \"RHS-100x50x4\", \"IBEAM-IPE200\", "
                    "\"ANGLE-65x65x6\", \"CHANNEL-100x50x5\", \"CHS-60x3\"."
                ),
            },
            "alignment": {
                "type": "string",
                "enum": ["centroid", "corner"],
                "description": (
                    "Profile alignment / justification. "
                    "\"centroid\" (default): profile centroid on the skeleton edge. "
                    "\"corner\": one corner of the profile on the skeleton edge."
                ),
            },
            "gap_mm": {
                "type": "number",
                "description": (
                    "Extra clearance gap (mm) added at each joint end beyond "
                    "the trim. Default 0.0."
                ),
            },
        },
        "required": ["skeleton", "profile"],
    },
)


@register(_weldment_frame_spec, write=False)
async def run_weldment_frame(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    skeleton  = a.get("skeleton", [])
    profile   = a.get("profile", "").strip()
    alignment = a.get("alignment", "centroid")
    gap_mm    = a.get("gap_mm", 0.0)

    if not profile:
        return err_payload("profile is required", "BAD_ARGS")

    try:
        gap_mm = float(gap_mm)
    except (TypeError, ValueError):
        return err_payload("gap_mm must be a number", "BAD_ARGS")
    if gap_mm < 0:
        return err_payload("gap_mm must be >= 0", "BAD_ARGS")

    if alignment not in ("centroid", "corner"):
        return err_payload("alignment must be 'centroid' or 'corner'", "BAD_ARGS")

    if not isinstance(skeleton, list):
        return err_payload("skeleton must be a list of edges", "BAD_ARGS")

    profile_data = lookup_profile(profile)
    if profile_data is None:
        return err_payload(
            f"unknown profile '{profile}'; use weldment_profile_lookup to browse",
            "UNKNOWN_PROFILE",
        )

    members, errors = compute_members(skeleton, profile_data, alignment, gap_mm)
    if errors:
        return json.dumps({"ok": False, "errors": errors})

    cutlist = compute_cutlist(members, profile_data)

    return ok_payload({
        "ok": True,
        "profile": profile,
        "alignment": alignment,
        "member_count": len(members),
        "members": members,
        "cutlist": cutlist,
    })


# ---------------------------------------------------------------------------
# T-2: weldment_profile_lookup
# ---------------------------------------------------------------------------

_weldment_profile_lookup_spec = ToolSpec(
    name="weldment_profile_lookup",
    description=(
        "Look up structural profile data by designation, or list all "
        "profiles in a given family. "
        "Returns area_mm2, mass_per_m_kg (kg/m, mild steel ρ=7850 kg/m³), "
        "and nominal outer dimensions. "
        "Families: SQ (square hollow), RHS (rectangular hollow), "
        "CHS (circular hollow / round tube), ANGLE (equal-leg angle), "
        "CHANNEL (parallel-flange channel), IBEAM (IPE I-beam). "
        "Pass designation for a single lookup, or family to list all profiles "
        "in that family.  Both optional: omit both to list all profiles."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "designation": {
                "type": "string",
                "description": (
                    "Exact profile key, e.g. \"SQ-50x50x3\", "
                    "\"IBEAM-IPE200\". If omitted, returns a list."
                ),
            },
            "family": {
                "type": "string",
                "enum": ["SQ", "RHS", "CHS", "ANGLE", "CHANNEL", "IBEAM"],
                "description": "Filter by profile family when listing.",
            },
        },
        "required": [],
    },
)


@register(_weldment_profile_lookup_spec, write=False)
async def run_weldment_profile_lookup(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    designation = a.get("designation", "").strip()
    family      = a.get("family", "").strip() or None

    if designation:
        pd = lookup_profile(designation)
        if pd is None:
            return json.dumps({
                "ok": False,
                "errors": [f"unknown profile '{designation}'"],
            })
        return ok_payload({"ok": True, "profile": pd})

    from kerf_cad_core.weldment_profiles import list_profiles
    profiles = list_profiles(family)
    return ok_payload({
        "ok": True,
        "family_filter": family,
        "count": len(profiles),
        "profiles": profiles,
    })


# ---------------------------------------------------------------------------
# T-3: weldment_cutlist
# ---------------------------------------------------------------------------

_weldment_cutlist_spec = ToolSpec(
    name="weldment_cutlist",
    description=(
        "Roll up a list of weldment members into a cut list grouped by "
        "profile designation. "
        "Input: the members list from weldment_frame (or a manually "
        "constructed list). Each member must have keys: "
        "``profile`` (designation), ``length_mm`` (float). "
        "Output: cut list sorted by designation, each entry with: "
        "pieces (length + quantity), total_length_mm, total_mass_kg. "
        "Also returns grand_total_mass_kg across all profiles. "
        "Handles multiple different profiles in one frame (mixed sections)."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "members": {
                "type": "array",
                "description": (
                    "Member list from weldment_frame, or custom. "
                    "Each element must have \"profile\" and \"length_mm\"."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "profile":   {"type": "string"},
                        "length_mm": {"type": "number"},
                    },
                    "required": ["profile", "length_mm"],
                },
            },
        },
        "required": ["members"],
    },
)


@register(_weldment_cutlist_spec, write=False)
async def run_weldment_cutlist(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    members = a.get("members", [])
    if not isinstance(members, list):
        return err_payload("members must be a list", "BAD_ARGS")

    if not members:
        return err_payload("members list is empty", "BAD_ARGS")

    # Validate and collect unique designations
    errors: list[str] = []
    profiles_needed: dict[str, dict] = {}
    for i, m in enumerate(members):
        if not isinstance(m, dict):
            errors.append(f"members[{i}]: must be an object")
            continue
        desig = m.get("profile", "")
        if not desig:
            errors.append(f"members[{i}]: 'profile' is required")
            continue
        try:
            float(m.get("length_mm", "invalid"))
        except (TypeError, ValueError):
            errors.append(f"members[{i}]: 'length_mm' must be a number")
            continue
        if desig not in profiles_needed:
            pd = lookup_profile(desig)
            if pd is None:
                errors.append(f"members[{i}]: unknown profile '{desig}'")
                continue
            profiles_needed[desig] = pd

    if errors:
        return json.dumps({"ok": False, "errors": errors})

    # Normalise length_mm to float
    clean_members = [
        {**m, "length_mm": float(m["length_mm"])} for m in members
    ]

    cutlist = compute_multi_cutlist(clean_members, profiles_needed)
    grand_total_mass = sum(c["total_mass_kg"] for c in cutlist)

    return ok_payload({
        "ok": True,
        "cutlist": cutlist,
        "grand_total_mass_kg": round(grand_total_mass, 6),
    })
