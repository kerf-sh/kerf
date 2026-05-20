"""GK-85  Body simplify / heal.

Pure-Python, no OCCT dependency.

Public API
----------
simplify_body(body, tol=1e-6) -> Body
    Remove sub-tolerance faces and edges, weld near-duplicate vertices.
    Returns a *new* Body (input is not mutated).

heal_body(body, tol=1e-6) -> Body
    Higher-level heal pass: runs simplify_body, then closes sliver gaps by
    re-checking loop closure and snapping coedge endpoints within ``tol``.
    Returns a *new* Body.

Design notes
------------
*   The implementation is deliberately OCCT-free — it operates on the
    :class:`~kerf_cad_core.geom.brep.Body` topology graph directly.
*   "Sub-tolerance edge" means ``edge.length() < tol``.  When all coedges of
    a face collapse to nothing the face is degenerate and is removed.
*   "Near-duplicate vertex" means two distinct :class:`Vertex` objects whose
    3-D positions are within ``tol`` of each other; the lower-id one is kept
    and all references updated.
*   Sliver-gap closure: after vertex welding the loop-closure check in
    :func:`~kerf_cad_core.geom.brep.validate_body` may still find small gaps
    (``< tol``) caused by imported precision mismatches.  ``heal_body`` snaps
    the endpoint of an edge to the start of the next coedge when the gap is
    within 10 × ``tol`` so that the loop becomes closed.
*   The returned Body uses *copies* of the topology so that the caller can
    keep using the original.
"""

from __future__ import annotations

import copy
from typing import Dict, List, Tuple

import numpy as np

from kerf_cad_core.geom.brep import (
    Body,
    Coedge,
    Edge,
    Face,
    Line3,
    Loop,
    Shell,
    Solid,
    Vertex,
)

__all__ = ["simplify_body", "heal_body"]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _collect_all_vertices(body: Body) -> List[Vertex]:
    """Return every Vertex reachable from *body* (dedup by identity)."""
    seen: set = set()
    out: List[Vertex] = []
    for e in body.all_edges():
        for v in (e.v_start, e.v_end):
            if id(v) not in seen:
                seen.add(id(v))
                out.append(v)
    # also pick up any anchor vertices in empty loops
    for lp in body.all_loops():
        av = getattr(lp, "_anchor_vertex", None)
        if av is not None and id(av) not in seen:
            seen.add(id(av))
            out.append(av)
    return out


def _weld_vertices(
    vertices: List[Vertex],
    tol: float,
) -> Dict[int, Vertex]:
    """Build an id -> canonical-Vertex map merging duplicates within *tol*.

    The vertex with the smallest ``id`` in each cluster is chosen as
    canonical, so the mapping is deterministic.
    """
    # Union-Find with path compression
    parent: Dict[int, Vertex] = {id(v): v for v in vertices}

    def root(v: Vertex) -> Vertex:
        rv = parent[id(v)]
        while id(rv) != id(parent[id(rv)]):
            # path compression
            parent[id(rv)] = parent[id(parent[id(rv)])]
            rv = parent[id(rv)]
        return rv

    def union(a: Vertex, b: Vertex) -> None:
        ra, rb = root(a), root(b)
        if id(ra) == id(rb):
            return
        # keep the lower-id vertex as canonical
        if ra.id <= rb.id:
            parent[id(rb)] = ra
        else:
            parent[id(ra)] = rb

    # O(N²) merge — bodies are small; for large bodies a spatial grid would
    # be used but that is out of scope for this pure-Python pass.
    for i, vi in enumerate(vertices):
        for j in range(i + 1, len(vertices)):
            vj = vertices[j]
            if float(np.linalg.norm(vi.point - vj.point)) <= tol:
                union(vi, vj)

    return {id(v): root(v) for v in vertices}


def _deep_copy_body(body: Body) -> Tuple[Body, Dict[int, object]]:
    """Return a deep copy of *body* together with an id-to-new-object map.

    The map allows the caller to resolve relationships (e.g. vertex
    references inside edges) after the copy.
    """
    new_body = copy.deepcopy(body)
    return new_body


def _rebuild_body(
    body: Body,
    tol: float,
    remove_short_edges: bool,
    snap_gaps: bool,
) -> Body:
    """Core reconstruction pass.

    1. Deep-copy the body to avoid mutating the caller's objects.
    2. Collect all vertices and build a weld map.
    3. Replace every v_start / v_end reference with the canonical vertex.
    4. Optionally remove edges whose length < *tol*.
    5. Drop faces whose outer loop has fewer than 2 surviving coedges
       (degenerate face).
    6. Optionally snap coedge endpoint gaps within 10*tol (sliver heal).
    7. Re-assemble the Body from surviving faces.
    """
    # Step 1 — deep copy
    new_body: Body = copy.deepcopy(body)

    # Step 2 — weld map on the copy
    all_verts = _collect_all_vertices(new_body)
    weld_map = _weld_vertices(all_verts, tol)

    # Step 3 — re-wire vertex references
    for e in new_body.all_edges():
        e.v_start = weld_map.get(id(e.v_start), e.v_start)
        e.v_end = weld_map.get(id(e.v_end), e.v_end)

    for lp in new_body.all_loops():
        av = getattr(lp, "_anchor_vertex", None)
        if av is not None:
            lp._anchor_vertex = weld_map.get(id(av), av)

    # Step 4 — remove sub-tolerance edges (only when requested)
    short_edge_ids: set = set()
    if remove_short_edges:
        for e in new_body.all_edges():
            try:
                if e.length() < tol:
                    short_edge_ids.add(id(e))
            except Exception:
                pass

    # Step 5 — rebuild shells, removing degenerate faces / coedges
    def _rebuild_shell(shell: Shell) -> Shell:
        new_faces: List[Face] = []
        for face in shell.faces:
            new_loops: List[Loop] = []
            for lp in face.loops:
                surviving = [
                    ce for ce in lp.coedges
                    if id(ce.edge) not in short_edge_ids
                ]
                if len(surviving) < 2 and lp.is_outer:
                    # outer loop collapsed → face is degenerate, skip it
                    break
                elif len(surviving) < 2 and not lp.is_outer:
                    # inner loop collapsed → just drop the hole
                    continue
                new_lp = Loop(surviving, is_outer=lp.is_outer)
                new_lp.face = face
                new_loops.append(new_lp)
            else:
                # only reaches here if we did NOT break (face not degenerate)
                if new_loops:
                    face.loops = new_loops
                    for lp in new_loops:
                        lp.face = face
                    new_faces.append(face)
                    continue
            # face was degenerate (we broke out of the inner for)
        new_shell = Shell(new_faces, is_closed=shell.is_closed)
        return new_shell

    # Rebuild solids
    new_solids: List[Solid] = []
    for solid in new_body.solids:
        new_shells: List[Shell] = []
        for shell in solid.shells:
            rebuilt = _rebuild_shell(shell)
            if rebuilt.faces:
                new_shells.append(rebuilt)
        if new_shells:
            new_solid = Solid(new_shells)
            new_solids.append(new_solid)

    # Rebuild free shells
    new_free_shells: List[Shell] = []
    for shell in new_body.shells:
        rebuilt = _rebuild_shell(shell)
        if rebuilt.faces:
            new_free_shells.append(rebuilt)

    result = Body(
        solids=new_solids,
        shells=new_free_shells,
        wires=list(new_body.wires),
    )

    # Step 6 — sliver gap snap
    if snap_gaps:
        _snap_loop_gaps(result, tol)

    return result


def _snap_loop_gaps(body: Body, tol: float) -> None:
    """In-place: snap coedge endpoints within 10*tol to close sliver gaps.

    When an imported body has tiny positional mismatches (e.g. 1e-9) the
    loop-closure check in validate_body will report gaps.  This pass
    nudges ``edge.v_end.point`` (for forward coedges) or ``edge.v_start.point``
    (for reversed ones) to exactly match the next coedge's start point when the
    gap is below the snap threshold.
    """
    snap_tol = 10.0 * tol
    for lp in body.all_loops():
        n = len(lp.coedges)
        if n < 1:
            continue
        for i, ce in enumerate(lp.coedges):
            nxt = lp.coedges[(i + 1) % n]
            end_pt = ce.end_point()
            start_pt = nxt.start_point()
            gap = float(np.linalg.norm(end_pt - start_pt))
            if 0 < gap <= snap_tol:
                # Snap the vertex of *ce* at its end to the position of
                # the vertex at the start of *nxt*.
                target = nxt.start_vertex().point.copy()
                end_v = ce.end_vertex()
                end_v.point = target
                # Also update the underlying curve endpoint if it is a Line3
                e = ce.edge
                if isinstance(e.curve, Line3):
                    if ce.orientation:
                        e.curve.p1 = target
                        e.v_end.point = target
                    else:
                        e.curve.p0 = target
                        e.v_start.point = target


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def simplify_body(body: Body, tol: float = 1e-6) -> Body:
    """Remove sub-tolerance faces and edges; weld near-duplicate vertices.

    Parameters
    ----------
    body:
        Input :class:`~kerf_cad_core.geom.brep.Body`.  Not mutated.
    tol:
        Tolerance threshold.  Edges shorter than *tol* are removed.
        Vertices within *tol* of each other are welded to the lowest-id
        representative.

    Returns
    -------
    Body
        A new :class:`~kerf_cad_core.geom.brep.Body` with sub-tolerance
        geometry removed.
    """
    if tol <= 0:
        raise ValueError(f"tol must be positive, got {tol!r}")
    return _rebuild_body(body, tol=tol, remove_short_edges=True, snap_gaps=False)


def heal_body(body: Body, tol: float = 1e-6) -> Body:
    """Simplify and close sliver gaps in *body*.

    Runs :func:`simplify_body` and then snaps coedge-endpoint gaps within
    ``10 * tol`` so that :func:`~kerf_cad_core.geom.brep.validate_body`
    reports a clean body for typical imported STEP/IGES bodies.

    Parameters
    ----------
    body:
        Input :class:`~kerf_cad_core.geom.brep.Body`.  Not mutated.
    tol:
        Tolerance threshold passed to both the simplify pass and the gap-snap
        pass.

    Returns
    -------
    Body
        A new healed :class:`~kerf_cad_core.geom.brep.Body`.
    """
    if tol <= 0:
        raise ValueError(f"tol must be positive, got {tol!r}")
    return _rebuild_body(body, tol=tol, remove_short_edges=True, snap_gaps=True)
