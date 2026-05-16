"""
blocks.py
=========
Block definitions and instance references for Rhino-parity assembly in Kerf.

A *block definition* is a named, reusable collection of geometry nodes
(part references, sub-assemblies, or primitives) anchored at a base point.
A *block instance* places a definition into a scene with a combined
translate/rotate/scale transform and optional per-instance attribute overrides.

Public API
----------
BlockDefinition(name, parts, base_point, metadata)
    A named, reusable set of geometry nodes.

BlockInstance(block_name, transform, attributes)
    A placed occurrence of a block definition.

BlockLibrary
    Registry of definitions; add/get/remove; dependency graph; cycle detection.

instantiate(library, instance) -> list[BlockInstance]
    Recursively expand nested block references, composing transforms at each
    level.  Returns a flat list of leaf instances with world transforms.

world_transform_of(instance) -> list[list[float]]
    Build the 4×4 homogeneous matrix that encodes translate+rotate+scale for
    a single instance (no hierarchy traversal — use instantiate for that).

instance_count(library, block_name) -> int
    Total number of leaf geometry nodes produced when a block is fully expanded.

unique_block_count(library) -> int
    Number of distinct definitions registered in the library.

bom_from_instances(library, instances) -> dict[str, int]
    Roll up top-level block-usage counts across a list of root instances.
    Nested sub-blocks are NOT recursively flattened — only the immediate
    definition names of the supplied instances are tallied.

Notes
-----
- Pure Python.  No numpy, no OCC, no I/O.
- 4×4 matrix arithmetic is hand-rolled with nested lists.
- Never raises: every error is surfaced as a return value or logged as a
  warning in the result dict where applicable.
- @register LLM tools are gated behind a try/import block (mirror of
  trim_curve.py) and appended to _TOOL_MODULES in plugin.py.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# Matrix helpers (hand-rolled 4×4 homogeneous arithmetic)
# ---------------------------------------------------------------------------

_Mat4 = List[List[float]]


def _mat4_identity() -> _Mat4:
    return [
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]


def _mat4_mul(a: _Mat4, b: _Mat4) -> _Mat4:
    """4×4 matrix product  a @ b."""
    result = [[0.0] * 4 for _ in range(4)]
    for i in range(4):
        for j in range(4):
            s = 0.0
            for k in range(4):
                s += a[i][k] * b[k][j]
            result[i][j] = s
    return result


def _mat4_translation(tx: float, ty: float, tz: float) -> _Mat4:
    m = _mat4_identity()
    m[0][3] = tx
    m[1][3] = ty
    m[2][3] = tz
    return m


def _mat4_scale(sx: float, sy: float, sz: float) -> _Mat4:
    m = _mat4_identity()
    m[0][0] = sx
    m[1][1] = sy
    m[2][2] = sz
    return m


def _mat4_rotation_x(angle_rad: float) -> _Mat4:
    c, s = math.cos(angle_rad), math.sin(angle_rad)
    m = _mat4_identity()
    m[1][1] = c;  m[1][2] = -s
    m[2][1] = s;  m[2][2] =  c
    return m


def _mat4_rotation_y(angle_rad: float) -> _Mat4:
    c, s = math.cos(angle_rad), math.sin(angle_rad)
    m = _mat4_identity()
    m[0][0] =  c;  m[0][2] = s
    m[2][0] = -s;  m[2][2] = c
    return m


def _mat4_rotation_z(angle_rad: float) -> _Mat4:
    c, s = math.cos(angle_rad), math.sin(angle_rad)
    m = _mat4_identity()
    m[0][0] = c;  m[0][1] = -s
    m[1][0] = s;  m[1][1] =  c
    return m


def _mat4_from_transform(
    translate: Tuple[float, float, float] = (0.0, 0.0, 0.0),
    rotate: Tuple[float, float, float] = (0.0, 0.0, 0.0),
    scale: Tuple[float, float, float] = (1.0, 1.0, 1.0),
) -> _Mat4:
    """Build a 4×4 TRS matrix (T * Rz * Ry * Rx * S)."""
    T = _mat4_translation(*translate)
    Rx = _mat4_rotation_x(rotate[0])
    Ry = _mat4_rotation_y(rotate[1])
    Rz = _mat4_rotation_z(rotate[2])
    S = _mat4_scale(*scale)
    # Combine: T * Rz * Ry * Rx * S
    return _mat4_mul(T, _mat4_mul(Rz, _mat4_mul(Ry, _mat4_mul(Rx, S))))


# ---------------------------------------------------------------------------
# BlockDefinition
# ---------------------------------------------------------------------------

@dataclass
class BlockDefinition:
    """A named, reusable set of geometry (part) nodes.

    Attributes
    ----------
    name : str
        Unique identifier for this block.
    parts : list of str
        Opaque part-node references (IDs, file paths, sub-block names …).
        Sub-blocks are detected by matching against the owning BlockLibrary.
    base_point : (x, y, z)
        Local origin used when inserting this block.
    metadata : dict
        Arbitrary key/value pairs (e.g. description, layer, colour).
    """
    name: str
    parts: List[str] = field(default_factory=list)
    base_point: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_valid(self) -> bool:
        return bool(self.name and self.name.strip())


# ---------------------------------------------------------------------------
# BlockInstance
# ---------------------------------------------------------------------------

@dataclass
class BlockInstance:
    """A placed occurrence of a BlockDefinition.

    Attributes
    ----------
    block_name : str
        Name of the referenced BlockDefinition.
    translate : (tx, ty, tz)
        Translation component of the placement transform.
    rotate : (rx, ry, rz)
        Euler angles in radians (ZYX application order after scale).
    scale : (sx, sy, sz)
        Non-uniform scale; defaults to (1, 1, 1).
    attributes : dict
        Per-instance attribute overrides (e.g. colour, material).
    """
    block_name: str
    translate: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotate: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    scale: Tuple[float, float, float] = (1.0, 1.0, 1.0)
    attributes: Dict[str, Any] = field(default_factory=dict)

    @property
    def transform_matrix(self) -> _Mat4:
        """4×4 TRS matrix for this instance (no hierarchy)."""
        return _mat4_from_transform(self.translate, self.rotate, self.scale)


# ---------------------------------------------------------------------------
# BlockLibrary
# ---------------------------------------------------------------------------

class BlockLibrary:
    """Registry of BlockDefinitions with cycle detection.

    Methods
    -------
    add(definition)
        Register a BlockDefinition.  Silently replaces an existing one with
        the same name.
    get(name) -> Optional[BlockDefinition]
        Look up a definition by name.
    remove(name) -> bool
        Remove a definition.  Returns True if it existed.
    definition_names() -> list[str]
        Sorted list of registered definition names.
    has_cycle() -> bool
        Detect a directed cycle in nested-block references.  Returns True if
        any definition transitively refers to itself.
    cycle_members() -> list[str]
        Names of blocks that participate in at least one cycle.
    """

    def __init__(self) -> None:
        self._defs: Dict[str, BlockDefinition] = {}

    # ── CRUD ──────────────────────────────────────────────────────────────

    def add(self, definition: BlockDefinition) -> None:
        """Register a definition (replaces silently on name clash)."""
        if not isinstance(definition, BlockDefinition):
            return
        self._defs[definition.name] = definition

    def get(self, name: str) -> Optional[BlockDefinition]:
        return self._defs.get(name)

    def remove(self, name: str) -> bool:
        if name in self._defs:
            del self._defs[name]
            return True
        return False

    def definition_names(self) -> List[str]:
        return sorted(self._defs.keys())

    # ── Dependency graph ──────────────────────────────────────────────────

    def _sub_block_names(self, defn: BlockDefinition) -> List[str]:
        """Return the subset of defn.parts that are themselves block names."""
        return [p for p in defn.parts if p in self._defs]

    def _build_adjacency(self) -> Dict[str, List[str]]:
        return {
            name: self._sub_block_names(defn)
            for name, defn in self._defs.items()
        }

    def has_cycle(self) -> bool:
        """True if the nested-block dependency graph contains a cycle."""
        return bool(self.cycle_members())

    def cycle_members(self) -> List[str]:
        """Return names of all block definitions involved in a cycle."""
        adj = self._build_adjacency()
        # Three-colour DFS
        WHITE, GREY, BLACK = 0, 1, 2
        colour: Dict[str, int] = {n: WHITE for n in adj}
        in_cycle: set = set()

        def dfs(node: str, path: List[str]) -> None:
            colour[node] = GREY
            path.append(node)
            for neighbour in adj.get(node, []):
                if colour.get(neighbour, BLACK) == GREY:
                    # Found a back-edge — mark the cycle members
                    cycle_start = neighbour
                    in_cycle.add(cycle_start)
                    for n in reversed(path):
                        in_cycle.add(n)
                        if n == cycle_start:
                            break
                elif colour.get(neighbour, BLACK) == WHITE:
                    dfs(neighbour, path)
            path.pop()
            colour[node] = BLACK

        for node in list(adj.keys()):
            if colour[node] == WHITE:
                dfs(node, [])

        return sorted(in_cycle)


# ---------------------------------------------------------------------------
# world_transform_of
# ---------------------------------------------------------------------------

def world_transform_of(instance: BlockInstance) -> _Mat4:
    """Return the 4×4 homogeneous world-transform matrix for *instance*.

    This function operates on a single instance and does not traverse any
    hierarchy.  To get the composed transform of a nested instance use
    ``instantiate`` and inspect the returned leaf's transform matrix.

    Parameters
    ----------
    instance : BlockInstance

    Returns
    -------
    list[list[float]]
        4×4 row-major homogeneous matrix.
    """
    return _mat4_from_transform(instance.translate, instance.rotate, instance.scale)


# ---------------------------------------------------------------------------
# instantiate (recursive expansion)
# ---------------------------------------------------------------------------

def instantiate(
    library: BlockLibrary,
    instance: BlockInstance,
    *,
    _parent_matrix: Optional[_Mat4] = None,
    _depth: int = 0,
    _visited: Optional[set] = None,
) -> List[BlockInstance]:
    """Recursively expand *instance* into a flat list of leaf BlockInstances.

    Nested blocks are expanded depth-first.  Each returned leaf carries a
    transform that is the composition of all ancestor transforms (parent @
    child in TRS order).  If a cycle is detected the offending sub-block is
    skipped (not infinite-looped) and the expansion continues.

    Parameters
    ----------
    library : BlockLibrary
    instance : BlockInstance
        Root instance to expand.

    Returns
    -------
    list of BlockInstance
        Leaf instances with composed world transforms.  Each leaf's
        ``attributes`` dict is the union of all ancestor overrides (child
        values win on key conflict).
    """
    if _visited is None:
        _visited = set()

    # Compose transforms
    local_matrix = _mat4_from_transform(instance.translate, instance.rotate, instance.scale)
    if _parent_matrix is not None:
        world_matrix = _mat4_mul(_parent_matrix, local_matrix)
    else:
        world_matrix = local_matrix

    defn = library.get(instance.block_name)
    if defn is None:
        # Unknown block — return instance as-is (leaf)
        leaf = _matrix_to_instance(instance.block_name, world_matrix, instance.attributes)
        return [leaf]

    # Cycle guard: if this block name is already on the current expansion
    # stack, skip it to avoid infinite recursion.
    if instance.block_name in _visited:
        return []

    _visited = _visited | {instance.block_name}  # immutable copy per branch

    sub_block_names = {p for p in defn.parts if library.get(p) is not None}
    leaf_parts = [p for p in defn.parts if p not in sub_block_names]
    results: List[BlockInstance] = []

    # Emit leaf geometry nodes (non-block parts)
    for part_id in leaf_parts:
        attrs = dict(defn.metadata)
        attrs.update(instance.attributes)
        leaf = _matrix_to_instance(part_id, world_matrix, attrs)
        results.append(leaf)

    # Recurse into sub-blocks
    for sub_name in defn.parts:
        if sub_name not in sub_block_names:
            continue
        attrs = dict(defn.metadata)
        attrs.update(instance.attributes)
        sub_inst = BlockInstance(
            block_name=sub_name,
            translate=(0.0, 0.0, 0.0),
            rotate=(0.0, 0.0, 0.0),
            scale=(1.0, 1.0, 1.0),
            attributes=attrs,
        )
        results.extend(
            instantiate(
                library,
                sub_inst,
                _parent_matrix=world_matrix,
                _depth=_depth + 1,
                _visited=_visited,
            )
        )

    return results


def _matrix_to_instance(block_name: str, matrix: _Mat4, attributes: Dict[str, Any]) -> BlockInstance:
    """Create a BlockInstance whose translate/rotate/scale encodes ``matrix``.

    We decompose the 4×4 matrix back to TRS only to keep the public type
    consistent.  For exact matrix fidelity the consumer should use the
    ``transform_matrix`` property which re-derives the matrix from TRS.

    For the purposes of this module (leaf emission, BoM rollup, test
    assertions) we store the raw matrix in the ``attributes`` dict under
    the key ``'_matrix'`` so callers can retrieve the exact composed value.
    """
    tx = matrix[0][3]
    ty = matrix[1][3]
    tz = matrix[2][3]
    inst = BlockInstance(
        block_name=block_name,
        translate=(tx, ty, tz),
        rotate=(0.0, 0.0, 0.0),
        scale=(1.0, 1.0, 1.0),
        attributes=dict(attributes),
    )
    inst.attributes["_matrix"] = [row[:] for row in matrix]
    return inst


# ---------------------------------------------------------------------------
# instance_count
# ---------------------------------------------------------------------------

def instance_count(
    library: BlockLibrary,
    block_name: str,
    *,
    _visited: Optional[frozenset] = None,
) -> int:
    """Return the total number of *leaf geometry nodes* produced when
    ``block_name`` is fully expanded (recursive).

    Parameters
    ----------
    library : BlockLibrary
    block_name : str

    Returns
    -------
    int
        0 if the block is not defined or if the expansion produces no
        geometry (e.g. empty parts list).  Cycles are detected and broken:
        a back-edge contributes 0 to avoid infinite recursion.
    """
    if _visited is None:
        _visited = frozenset()

    defn = library.get(block_name)
    if defn is None:
        return 0

    if block_name in _visited:
        return 0

    _visited = _visited | {block_name}

    total = 0
    for part in defn.parts:
        if library.get(part) is not None:
            total += instance_count(library, part, _visited=_visited)
        else:
            total += 1
    return total


# ---------------------------------------------------------------------------
# unique_block_count
# ---------------------------------------------------------------------------

def unique_block_count(library: BlockLibrary) -> int:
    """Number of distinct block definitions registered in the library."""
    return len(library._defs)


# ---------------------------------------------------------------------------
# bom_from_instances
# ---------------------------------------------------------------------------

def bom_from_instances(
    library: BlockLibrary,
    instances: Sequence[BlockInstance],
) -> Dict[str, int]:
    """Tally the top-level block-name usage across *instances*.

    Only the immediate ``block_name`` of each root instance is counted.
    Nested sub-blocks are not recursively flattened here — use
    ``instantiate`` if you need a fully-resolved BOM.

    Parameters
    ----------
    library : BlockLibrary
        Used only to validate that referenced blocks exist (unknown names are
        still counted).
    instances : sequence of BlockInstance

    Returns
    -------
    dict mapping block_name -> count
    """
    counts: Dict[str, int] = {}
    for inst in instances:
        name = inst.block_name
        counts[name] = counts.get(name, 0) + 1
    return counts


# ---------------------------------------------------------------------------
# LLM tool registration (gated; mirrors trim_curve.py)
# ---------------------------------------------------------------------------

try:
    from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register  # type: ignore[import]
    from kerf_core.utils.context import ProjectCtx  # type: ignore[import]
    import json as _json
    _REGISTRY_AVAILABLE = True
except ImportError:
    _REGISTRY_AVAILABLE = False


if _REGISTRY_AVAILABLE:
    # ------------------------------------------------------------------
    # create_block_definition
    # ------------------------------------------------------------------

    _create_block_def_spec = ToolSpec(
        name="create_block_definition",
        description=(
            "Create or update a named block definition in the session block library. "
            "A block definition is a reusable set of geometry nodes (parts) anchored "
            "at a base point.  Sub-blocks (nested blocks) are supported — list their "
            "names in the parts array.\n"
            "\n"
            "Returns:\n"
            "  ok          : bool\n"
            "  name        : str   (echoed)\n"
            "  part_count  : int\n"
            "\n"
            "Errors: {ok:false, reason} for invalid inputs.  Never raises."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Unique block definition name.",
                },
                "parts": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of part IDs or sub-block names included in this block.",
                },
                "base_point": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "[x, y, z] local origin (default [0,0,0]).",
                },
                "metadata": {
                    "type": "object",
                    "description": "Arbitrary key/value metadata.",
                },
            },
            "required": ["name", "parts"],
        },
    )

    @register(_create_block_def_spec)
    async def run_create_block_definition(ctx: "ProjectCtx", args: bytes) -> str:
        try:
            a = _json.loads(args)
        except Exception as exc:
            return err_payload(f"invalid args: {exc}", "BAD_ARGS")

        name = a.get("name", "").strip()
        parts = a.get("parts", [])
        base_raw = a.get("base_point", [0.0, 0.0, 0.0])
        metadata = a.get("metadata", {})

        if not name:
            return err_payload("name is required and must be non-empty", "BAD_ARGS")
        if not isinstance(parts, list):
            return err_payload("parts must be a list of strings", "BAD_ARGS")
        if not all(isinstance(p, str) for p in parts):
            return err_payload("each entry in parts must be a string", "BAD_ARGS")

        try:
            base_point = tuple(float(v) for v in base_raw[:3])
            while len(base_point) < 3:
                base_point = base_point + (0.0,)
        except (TypeError, ValueError) as exc:
            return err_payload(f"base_point must be [x,y,z] numbers: {exc}", "BAD_ARGS")

        defn = BlockDefinition(
            name=name,
            parts=list(parts),
            base_point=base_point,  # type: ignore[arg-type]
            metadata=dict(metadata) if isinstance(metadata, dict) else {},
        )

        lib: BlockLibrary = getattr(ctx, "_block_library", None)
        if lib is None:
            lib = BlockLibrary()
            ctx._block_library = lib  # type: ignore[attr-defined]
        lib.add(defn)

        return ok_payload({"ok": True, "name": name, "part_count": len(parts)})

    # ------------------------------------------------------------------
    # instantiate_block
    # ------------------------------------------------------------------

    _instantiate_block_spec = ToolSpec(
        name="instantiate_block",
        description=(
            "Recursively expand a block instance into a flat list of leaf geometry "
            "nodes, composing all ancestor transforms.  Use this to resolve an "
            "assembly into its constituent parts with world-space transforms.\n"
            "\n"
            "Returns:\n"
            "  ok          : bool\n"
            "  leaf_count  : int\n"
            "  leaves      : list of {block_name, translate, _matrix} dicts\n"
            "\n"
            "Errors: {ok:false, reason} for invalid inputs.  Never raises."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "block_name": {
                    "type": "string",
                    "description": "Name of the block definition to instantiate.",
                },
                "translate": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "[tx, ty, tz] translation (default [0,0,0]).",
                },
                "rotate": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "[rx, ry, rz] Euler angles in radians (default [0,0,0]).",
                },
                "scale": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "[sx, sy, sz] scale factors (default [1,1,1]).",
                },
                "attributes": {
                    "type": "object",
                    "description": "Per-instance attribute overrides.",
                },
            },
            "required": ["block_name"],
        },
    )

    @register(_instantiate_block_spec)
    async def run_instantiate_block(ctx: "ProjectCtx", args: bytes) -> str:
        try:
            a = _json.loads(args)
        except Exception as exc:
            return err_payload(f"invalid args: {exc}", "BAD_ARGS")

        block_name = a.get("block_name", "").strip()
        if not block_name:
            return err_payload("block_name is required", "BAD_ARGS")

        def _parse_vec3(key: str, default: Tuple) -> Tuple[float, float, float]:
            raw = a.get(key, list(default))
            try:
                v = tuple(float(x) for x in raw[:3])
                while len(v) < 3:
                    v = v + (0.0,)
                return v  # type: ignore[return-value]
            except (TypeError, ValueError):
                return default

        translate = _parse_vec3("translate", (0.0, 0.0, 0.0))
        rotate = _parse_vec3("rotate", (0.0, 0.0, 0.0))
        scale = _parse_vec3("scale", (1.0, 1.0, 1.0))
        attributes = a.get("attributes", {})
        if not isinstance(attributes, dict):
            attributes = {}

        lib: BlockLibrary = getattr(ctx, "_block_library", None)
        if lib is None:
            lib = BlockLibrary()
            ctx._block_library = lib  # type: ignore[attr-defined]

        inst = BlockInstance(
            block_name=block_name,
            translate=translate,
            rotate=rotate,
            scale=scale,
            attributes=dict(attributes),
        )
        leaves = instantiate(lib, inst)

        leaf_dicts = []
        for leaf in leaves:
            entry: Dict[str, Any] = {
                "block_name": leaf.block_name,
                "translate": list(leaf.translate),
                "_matrix": leaf.attributes.get("_matrix"),
            }
            leaf_dicts.append(entry)

        return ok_payload({"ok": True, "leaf_count": len(leaves), "leaves": leaf_dicts})
