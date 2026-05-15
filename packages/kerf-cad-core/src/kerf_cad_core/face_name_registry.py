"""
face_name_registry.py — T-13/T-14: Persistent face-naming boolean hardening.

This module provides pure-Python, OCC-optional machinery for:

1. **FaceSignature** — a stable geometric fingerprint (centroid, normal, area)
   that survives round-trips through the OCCT history-map when that map is
   available, and acts as the primary matching key when it is not.

2. **FaceNameRegistry** — a two-way map between persistent face names
   (strings like "pad-1.TopCap") and FaceSignatures.

3. **remap_face_ids_across_boolean** — given a *pre-boolean* registry snapshot
   and a *post-boolean* snapshot (both represented as dicts keyed by face-name
   or by signature), deterministically re-assigns names to post-boolean faces by
   matching signatures.  When OCCT's Modified/Generated history maps ARE
   available (OCC codepath), they are used first; signature matching is the
   fallback for faces that history cannot resolve.

4. **face_name_audit** — walks a feature-document dict and returns a list of
   ``AuditWarning`` items for every face reference that is either absent from
   the registry or whose signature has drifted since the name was assigned.

Design constraints
------------------
- Zero OCC dependency in the pure-Python path.  OCC-dependent helpers are
  inside the ``if _OCC_AVAILABLE:`` block and are never called from tests that
  run without OCC.
- Deterministic tie-breaking: when two post-boolean faces have the same
  signature distance to a pre-boolean face, the lexicographically-smallest
  face name is preferred.  This ensures re-running an op yields the same
  assignment.
- Collision handling: if two pre-boolean faces produce identical signatures
  (e.g. a shape with two symmetric coplanar faces), the registry appends a
  disambiguation suffix ``#0``, ``#1``, …  The suffix is stable as long as
  the iteration order of the input list is stable (i.e. the face index order
  from OCCT's TopExp_Explorer, which is deterministic for a given solid).
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, NamedTuple, Optional, Sequence, Tuple

from kerf_cad_core.occ_helpers import _OCC_AVAILABLE

# ---------------------------------------------------------------------------
# FaceSignature
# ---------------------------------------------------------------------------

# Precision used when hashing floating-point values.  Coordinates are rounded
# to this many decimal places before hashing so that tiny numerical noise from
# OCCT tessellators does not produce different hashes for the same face.
_COORD_DECIMALS = 4
_AREA_DECIMALS = 6


@dataclass(frozen=True)
class FaceSignature:
    """
    Stable geometric fingerprint for a B-rep face.

    All three components are expressed in the model's native units and are
    normalised before hashing:
      - centroid: (x, y, z) rounded to ``_COORD_DECIMALS`` decimal places.
      - normal:   unit-vector (nx, ny, nz) rounded; may be (0, 0, 0) for faces
                  whose normal is undefined (e.g. degenerate faces).
      - area:     surface area rounded to ``_AREA_DECIMALS``.

    The ``.hex`` property returns a 16-character hex digest that is fast to
    store and compare.
    """

    centroid: Tuple[float, float, float]
    normal: Tuple[float, float, float]
    area: float

    # Cached hex digest (computed lazily, frozen dataclass so set via
    # object.__setattr__ in __post_init__).
    _hex: str = field(default="", init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        # Normalise components
        cx, cy, cz = (round(v, _COORD_DECIMALS) for v in self.centroid)
        nx, ny, nz = (round(v, _COORD_DECIMALS) for v in self.normal)
        a = round(self.area, _AREA_DECIMALS)
        object.__setattr__(self, "centroid", (cx, cy, cz))
        object.__setattr__(self, "normal", (nx, ny, nz))
        object.__setattr__(self, "area", a)
        # Build hex digest
        raw = f"{cx},{cy},{cz}|{nx},{ny},{nz}|{a}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
        object.__setattr__(self, "_hex", digest)

    @property
    def hex(self) -> str:
        return self._hex

    def distance(self, other: "FaceSignature") -> float:
        """
        Euclidean distance in centroid-space (used as the primary match metric).

        The normal and area components are used as secondary tie-breakers via
        ``match_score`` — this method is kept simple for use in spatial sorting.
        """
        dx = self.centroid[0] - other.centroid[0]
        dy = self.centroid[1] - other.centroid[1]
        dz = self.centroid[2] - other.centroid[2]
        return math.sqrt(dx * dx + dy * dy + dz * dz)

    def match_score(self, other: "FaceSignature") -> float:
        """
        Combined match score: lower is better.

        Weighted sum of centroid distance + normal angle deviation +
        normalised area difference.  All three components are in [0, ∞) so the
        sum is a proper monotone metric.
        """
        centroid_dist = self.distance(other)

        # Normal angle deviation (dot product, clamped to [-1, 1])
        dot = (
            self.normal[0] * other.normal[0]
            + self.normal[1] * other.normal[1]
            + self.normal[2] * other.normal[2]
        )
        dot = max(-1.0, min(1.0, dot))
        angle_dev = math.acos(dot)  # radians in [0, π]

        # Area difference (relative, capped at 1)
        denom = max(self.area, other.area, 1e-12)
        area_diff = abs(self.area - other.area) / denom

        return centroid_dist + 0.5 * angle_dev + 0.3 * area_diff


def make_signature_from_dict(d: Dict[str, Any]) -> FaceSignature:
    """
    Build a FaceSignature from a plain dict with keys:
      ``centroid`` ([x, y, z]), ``normal`` ([nx, ny, nz]), ``area`` (float).

    Missing or malformed keys produce zero/unit defaults rather than raising,
    so a partial record still produces a usable (if imprecise) signature.
    """
    c = d.get("centroid") or [0.0, 0.0, 0.0]
    n = d.get("normal") or [0.0, 0.0, 1.0]
    a = float(d.get("area") or 0.0)
    cx, cy, cz = float(c[0]), float(c[1]), float(c[2])
    nx, ny, nz = float(n[0]), float(n[1]), float(n[2])
    return FaceSignature(centroid=(cx, cy, cz), normal=(nx, ny, nz), area=a)


# ---------------------------------------------------------------------------
# FaceNameRegistry
# ---------------------------------------------------------------------------


class FaceNameRegistry:
    """
    Bi-directional map: face_name ↔ FaceSignature.

    Insertion collision policy
    --------------------------
    If two calls to ``assign`` produce the same signature hex for different
    names, both are stored — the hex→name direction is a list (multiple names
    may share a signature when faces are geometrically identical, e.g.
    symmetrical faces on a prism).

    If the same name is re-assigned with a different signature, the old
    signature entry is replaced (the name wins; signatures may drift across
    geometry edits).
    """

    def __init__(self) -> None:
        self._name_to_sig: Dict[str, FaceSignature] = {}
        self._hex_to_names: Dict[str, List[str]] = {}

    # ── mutation ─────────────────────────────────────────────────────────────

    def assign(self, name: str, sig: FaceSignature) -> None:
        """
        Register or update the signature for ``name``.

        If the name was previously registered with a different signature, the
        old signature's reverse-index entry is cleaned up.
        """
        old = self._name_to_sig.get(name)
        if old is not None and old.hex != sig.hex:
            # Remove stale reverse entry
            old_list = self._hex_to_names.get(old.hex, [])
            if name in old_list:
                old_list.remove(name)
            if not old_list:
                self._hex_to_names.pop(old.hex, None)

        self._name_to_sig[name] = sig
        bucket = self._hex_to_names.setdefault(sig.hex, [])
        if name not in bucket:
            bucket.append(name)
            bucket.sort()  # deterministic order

    def remove(self, name: str) -> Optional[FaceSignature]:
        """Deregister a name.  Returns the old signature or None."""
        sig = self._name_to_sig.pop(name, None)
        if sig is not None:
            bucket = self._hex_to_names.get(sig.hex, [])
            if name in bucket:
                bucket.remove(name)
            if not bucket:
                self._hex_to_names.pop(sig.hex, None)
        return sig

    # ── lookup ────────────────────────────────────────────────────────────────

    def signature_for(self, name: str) -> Optional[FaceSignature]:
        """Return the stored FaceSignature for ``name``, or None."""
        return self._name_to_sig.get(name)

    def names_for_hex(self, hex_digest: str) -> List[str]:
        """Return all names whose signature has this hex digest (usually 0 or 1)."""
        return list(self._hex_to_names.get(hex_digest, []))

    def has(self, name: str) -> bool:
        return name in self._name_to_sig

    def all_names(self) -> List[str]:
        return sorted(self._name_to_sig.keys())

    def all_signatures(self) -> List[FaceSignature]:
        return list(self._name_to_sig.values())

    # ── nearest-match ─────────────────────────────────────────────────────────

    def find_nearest(
        self,
        sig: FaceSignature,
        max_distance: float = 1e6,
    ) -> Optional[str]:
        """
        Return the name whose signature is nearest to ``sig`` by match_score.

        Returns None when the registry is empty or no name is within
        ``max_distance`` in centroid-space.
        """
        best_name: Optional[str] = None
        best_score = math.inf
        for name, stored_sig in self._name_to_sig.items():
            if stored_sig.distance(sig) > max_distance:
                continue
            score = stored_sig.match_score(sig)
            if score < best_score or (
                score == best_score and (best_name is None or name < best_name)
            ):
                best_score = score
                best_name = name
        return best_name

    # ── snapshot / restore ────────────────────────────────────────────────────

    def snapshot(self) -> Dict[str, Dict[str, Any]]:
        """
        Return a JSON-serialisable dict mapping name → {centroid, normal, area}.
        Useful for storing the registry alongside a feature document.
        """
        result: Dict[str, Dict[str, Any]] = {}
        for name, sig in self._name_to_sig.items():
            result[name] = {
                "centroid": list(sig.centroid),
                "normal": list(sig.normal),
                "area": sig.area,
                "hex": sig.hex,
            }
        return result

    @classmethod
    def from_snapshot(cls, data: Dict[str, Dict[str, Any]]) -> "FaceNameRegistry":
        """Restore a registry from a snapshot dict."""
        reg = cls()
        for name, d in data.items():
            sig = make_signature_from_dict(d)
            reg.assign(name, sig)
        return reg

    def __len__(self) -> int:
        return len(self._name_to_sig)

    def __repr__(self) -> str:
        return f"FaceNameRegistry({len(self)} entries)"


# ---------------------------------------------------------------------------
# BooleanFaceMapper — pre/post boolean remapping
# ---------------------------------------------------------------------------


class RemapResult(NamedTuple):
    """
    Return value of ``remap_face_ids_across_boolean``.

    Attributes
    ----------
    remapped : dict[str, str]
        Maps post-boolean face ids (opaque string keys from the caller, e.g.
        "face-0", "face-1", …) to the persistent face names that should be
        assigned to them.

    unmatched_pre : list[str]
        Names from the pre-boolean registry that were NOT matched to any
        post-boolean face.  These are faces that were consumed/destroyed by
        the boolean op (e.g. the internal coincident faces of a fuse).

    unmatched_post : list[str]
        Post-boolean face ids that were NOT matched to any pre-boolean name.
        These are *new* faces created by the boolean op (intersection boundary
        faces).  The caller is responsible for assigning stable names to them;
        ``assign_new_boundary_names`` provides a deterministic naming strategy.
    """

    remapped: Dict[str, str]
    unmatched_pre: List[str]
    unmatched_post: List[str]


def remap_face_ids_across_boolean(
    pre_registry: FaceNameRegistry,
    post_faces: Dict[str, FaceSignature],
    op_kind: str = "fuse",
    history_map: Optional[Dict[str, str]] = None,
    max_distance: float = 1e6,
) -> RemapResult:
    """
    Match pre-boolean persistent face names to post-boolean faces.

    Parameters
    ----------
    pre_registry : FaceNameRegistry
        The registry snapshot taken BEFORE the boolean op.  Contains all
        named faces from both operands (A and B).

    post_faces : dict[str, FaceSignature]
        Mapping from an opaque post-boolean face id (e.g. "face-0") to the
        FaceSignature computed for that face AFTER the boolean.

    op_kind : str
        One of "fuse", "cut", "common".  Used only for logging / audit; the
        core algorithm is the same for all three.

    history_map : dict[str, str] | None
        Optional OCCT history map: maps post_face_id → pre_face_name.
        When provided, entries in this map are accepted first (history takes
        priority over signature matching); unresolved entries fall through
        to signature matching.

    max_distance : float
        Maximum centroid distance to consider a match (default 1e6 = no
        effective limit).  Tighten for dense geometry where false positives
        are a concern.

    Returns
    -------
    RemapResult
        See class docstring.

    Algorithm
    ---------
    1. Apply ``history_map`` entries (if any) — these are authoritative.
    2. For remaining unmatched post-faces, find the nearest pre-name by
       ``match_score``.  Each pre-name may be consumed by at most ONE
       post-face (greedy nearest-neighbour with score-order priority).
    3. Post-faces with no match within ``max_distance`` go to
       ``unmatched_post``.  Pre-names with no matching post-face go to
       ``unmatched_pre``.

    Tie-breaking
    ------------
    When two post-faces score equally against the same pre-name, the
    lexicographically-smaller post-face id wins (deterministic).
    """
    remapped: Dict[str, str] = {}
    used_pre_names: set = set()
    used_post_ids: set = set()

    # ── Step 1: apply history map ─────────────────────────────────────────────
    if history_map:
        for post_id, pre_name in sorted(history_map.items()):
            if pre_registry.has(pre_name) and post_id in post_faces:
                remapped[post_id] = pre_name
                used_pre_names.add(pre_name)
                used_post_ids.add(post_id)

    # ── Step 2: signature-based nearest-neighbour for remaining faces ─────────
    # Build candidate pairs: (score, post_id, pre_name) sorted by score asc,
    # then post_id asc for determinism.
    Candidate = Tuple[float, str, str]
    candidates: List[Candidate] = []

    remaining_post = {
        pid: sig for pid, sig in post_faces.items() if pid not in used_post_ids
    }
    remaining_pre_names = [
        n for n in pre_registry.all_names() if n not in used_pre_names
    ]

    for post_id, post_sig in remaining_post.items():
        for pre_name in remaining_pre_names:
            pre_sig = pre_registry.signature_for(pre_name)
            if pre_sig is None:
                continue
            dist = pre_sig.distance(post_sig)
            if dist > max_distance:
                continue
            score = pre_sig.match_score(post_sig)
            candidates.append((score, post_id, pre_name))

    # Sort: best score first, then lexicographic post_id for ties.
    candidates.sort(key=lambda c: (c[0], c[1], c[2]))

    for score, post_id, pre_name in candidates:
        if post_id in used_post_ids or pre_name in used_pre_names:
            continue
        remapped[post_id] = pre_name
        used_post_ids.add(post_id)
        used_pre_names.add(pre_name)

    # ── Step 3: collect unmatched ─────────────────────────────────────────────
    unmatched_post = sorted(
        pid for pid in post_faces if pid not in used_post_ids
    )
    unmatched_pre = sorted(
        n for n in pre_registry.all_names() if n not in used_pre_names
    )

    return RemapResult(
        remapped=remapped,
        unmatched_pre=unmatched_pre,
        unmatched_post=unmatched_post,
    )


def assign_new_boundary_names(
    boolean_node_id: str,
    op_kind: str,
    unmatched_post_ids: Sequence[str],
) -> Dict[str, str]:
    """
    Assign deterministic persistent names to faces that were CREATED by a
    boolean op (boundary faces — the intersection of the two operands).

    Naming convention: ``<boolean_node_id>.boundary.<op_kind>.<index>``

    Example: ``boolean-1.boundary.fuse.0``, ``boolean-1.boundary.fuse.1``

    The index is derived from the sorted order of ``unmatched_post_ids`` so the
    mapping is stable across re-evaluations as long as post-face ids are stable.

    Returns a dict mapping post_face_id → new persistent name.
    """
    result: Dict[str, str] = {}
    for idx, post_id in enumerate(sorted(unmatched_post_ids)):
        result[post_id] = f"{boolean_node_id}.boundary.{op_kind}.{idx}"
    return result


# ---------------------------------------------------------------------------
# face_name_audit
# ---------------------------------------------------------------------------


class AuditWarning(NamedTuple):
    """
    Describes a problem found by ``face_name_audit``.

    Attributes
    ----------
    node_id : str
        The id of the feature node that carries the problematic reference.

    face_name_key : str
        The JSON key under which the reference is stored (e.g.
        "target_face_name", "face_name").

    face_name_value : str
        The current stored value.

    kind : str
        One of:
          "UNMAPPED"  — name not present in the registry at all.
          "DRIFTED"   — name is registered but its stored signature has
                        drifted (caller supplied a current-geometry snapshot
                        via ``current_sigs``).
    """

    node_id: str
    face_name_key: str
    face_name_value: str
    kind: str


# Keys that store persistent face-name references in feature nodes.
_FACE_NAME_KEYS = frozenset({
    "target_face_name",
    "face_name",
})

# Drift tolerance: if a registered face's centroid has moved more than this
# many model units, we flag it as DRIFTED.
_DRIFT_CENTROID_THRESHOLD = 0.01  # 0.01 mm in mm-unit models


def face_name_audit(
    feature_doc: Dict[str, Any],
    registry: FaceNameRegistry,
    current_sigs: Optional[Dict[str, FaceSignature]] = None,
) -> List[AuditWarning]:
    """
    Walk a feature document and return warnings for every face reference that is
    either absent from ``registry`` or whose signature has drifted.

    Parameters
    ----------
    feature_doc : dict
        A parsed `.feature` JSON document (must have a ``"features"`` list).

    registry : FaceNameRegistry
        The current registry to validate against.

    current_sigs : dict[str, FaceSignature] | None
        Optional mapping from face_name → current FaceSignature.  When
        provided, registered names whose stored signature differs from the
        current signature by more than ``_DRIFT_CENTROID_THRESHOLD`` are
        flagged as DRIFTED.  When omitted, drift detection is skipped.

    Returns
    -------
    list[AuditWarning]
        Empty list means all face references are valid.  Warnings are in
        document order (node order × key order within a node).
    """
    warnings: List[AuditWarning] = []
    features = feature_doc.get("features", [])
    if not isinstance(features, list):
        return warnings

    for node in features:
        if not isinstance(node, dict):
            continue
        node_id = node.get("id") or node.get("op") or "<unknown>"

        for key in sorted(_FACE_NAME_KEYS):
            val = node.get(key)
            if not val or not str(val).strip():
                continue
            face_name = str(val).strip()

            if not registry.has(face_name):
                warnings.append(
                    AuditWarning(
                        node_id=node_id,
                        face_name_key=key,
                        face_name_value=face_name,
                        kind="UNMAPPED",
                    )
                )
                continue

            # Drift check
            if current_sigs and face_name in current_sigs:
                stored_sig = registry.signature_for(face_name)
                current_sig = current_sigs[face_name]
                if (
                    stored_sig is not None
                    and stored_sig.distance(current_sig) > _DRIFT_CENTROID_THRESHOLD
                ):
                    warnings.append(
                        AuditWarning(
                            node_id=node_id,
                            face_name_key=key,
                            face_name_value=face_name,
                            kind="DRIFTED",
                        )
                    )

    return warnings


# ---------------------------------------------------------------------------
# OCC-backed helpers (gated behind _OCC_AVAILABLE)
# ---------------------------------------------------------------------------

if _OCC_AVAILABLE:  # pragma: no cover — only exercised with OCC installed
    def _sig_from_occ_face(face: Any) -> Optional[FaceSignature]:
        """
        Compute a FaceSignature from an OCC TopoDS_Face.

        Uses BRepGProp for area + centroid, BRepAdaptor_Surface for normal at
        the UV midpoint of the face's parameter bounds.

        Returns None if any computation fails (degenerate face, etc.).
        """
        try:
            from OCC.Core.BRepGProp import brepgprop_SurfaceProperties  # type: ignore
            from OCC.Core.GProp import GProp_GProps  # type: ignore
            from OCC.Core.BRepAdaptor import BRepAdaptor_Surface  # type: ignore
            from OCC.Core.GeomAbs import GeomAbs_SurfaceType  # type: ignore

            props = GProp_GProps()
            brepgprop_SurfaceProperties(face, props)
            area = props.Mass()
            g = props.CentreOfMass()
            cx, cy, cz = g.X(), g.Y(), g.Z()

            # Normal at UV midpoint
            adaptor = BRepAdaptor_Surface(face)
            u0, u1 = adaptor.FirstUParameter(), adaptor.LastUParameter()
            v0, v1 = adaptor.FirstVParameter(), adaptor.LastVParameter()
            u_mid = (u0 + u1) * 0.5
            v_mid = (v0 + v1) * 0.5

            pnt = adaptor.Value(u_mid, v_mid)
            from OCC.Core.gp import gp_Vec  # type: ignore
            d1u = gp_Vec()
            d1v = gp_Vec()
            pnt2 = adaptor.Value(u_mid + 1e-7, v_mid)
            d1u = gp_Vec(
                pnt2.X() - pnt.X(),
                pnt2.Y() - pnt.Y(),
                pnt2.Z() - pnt.Z(),
            )
            pnt3 = adaptor.Value(u_mid, v_mid + 1e-7)
            d1v = gp_Vec(
                pnt3.X() - pnt.X(),
                pnt3.Y() - pnt.Y(),
                pnt3.Z() - pnt.Z(),
            )
            n = d1u.Crossed(d1v)
            mag = n.Magnitude()
            if mag > 1e-15:
                n.Normalize()
            nx, ny, nz = n.X(), n.Y(), n.Z()
            return FaceSignature(
                centroid=(cx, cy, cz),
                normal=(nx, ny, nz),
                area=area,
            )
        except Exception:
            return None

    def build_registry_from_occ_shape(
        shape: Any,
        name_prefix: str,
        registry: Optional[FaceNameRegistry] = None,
    ) -> FaceNameRegistry:
        """
        Enumerate all faces of an OCC shape and populate a FaceNameRegistry.

        Each face is named ``<name_prefix>.face<i>`` where ``i`` is its
        0-based index in TopExp_Explorer order.  When two faces produce
        identical signatures, a ``#<j>`` disambiguation suffix is appended.

        If ``registry`` is None, a new one is created; otherwise the shape's
        faces are merged into the existing registry (useful for building a
        combined A+B pre-boolean registry).
        """
        from OCC.Core.TopExp import TopExp_Explorer  # type: ignore
        from OCC.Core.TopAbs import TopAbs_FACE  # type: ignore

        if registry is None:
            registry = FaceNameRegistry()

        seen_hexes: Dict[str, int] = {}
        explorer = TopExp_Explorer(shape, TopAbs_FACE)
        i = 0
        while explorer.More():
            face = explorer.Current()
            sig = _sig_from_occ_face(face)
            if sig is not None:
                base_name = f"{name_prefix}.face{i}"
                hex_d = sig.hex
                count = seen_hexes.get(hex_d, 0)
                name = base_name if count == 0 else f"{base_name}#{count}"
                seen_hexes[hex_d] = count + 1
                registry.assign(name, sig)
            explorer.Next()
            i += 1

        return registry
