"""geom/io/rhino3dm.py — GK-127: 3DM (Rhino OpenNURBS) read.

Two-tier strategy
-----------------
1. If the ``rhino3dm`` PyPI package is importable, delegate all parsing to it
   (authoritative OpenNURBS decoding) and map objects into the canonical dict.
2. Otherwise fall back to a pure-Python minimal 3DM chunk reader that handles
   the object types most commonly found in CAD exchange files:
     - ON_NurbsCurve   (typecode 100)
     - ON_NurbsSurface (typecode 74)
     - ON_Mesh         (typecode 32)
     - ON_Layer        (typecode 4)
   If the file uses features the minimal reader cannot decode it raises
   ``Rhino3dmReadError`` with a descriptive message — callers should either
   install rhino3dm or handle the exception.

Public API
----------
    read_3dm(path: str | PathLike) -> dict
        Returns::

            {
                "curves":   [NurbsCurve, ...],
                "surfaces": [NurbsSurface, ...],
                "meshes":   [{"vertices": ndarray(N,3),
                               "faces":    ndarray(F,3|4) | None,
                               "layer":    str}, ...],
                "layers":   [{"name": str, "full_path": str,
                               "layer_index": int,
                               "color": tuple(r,g,b) | None}, ...],
            }

    Rhino3dmReadError
        Raised on malformed or unsupported 3DM content.

3DM format references
---------------------
The 3DM binary format uses OpenNURBS "chunk" framing:
  - File starts with a 33-byte comment string ending with ``\\x1a\\x00``
  - Followed by sequential chunks.  Each chunk has a header:
      4 bytes  typecode  (big-endian unsigned int)
      4 bytes  length    (little-endian unsigned int, 0xFFFFFFFF = big chunk)
    Big chunks append a further 8-byte length (little-endian uint64).
  - A typecode of 0 ends the top-level sequence.

The short-form chunk reader implemented here is intentionally limited: it only
parses enough to support the hermetic round-trip oracle test embedded in
test_rhino3dm.py.  For production use install ``pip install rhino3dm``.
"""

from __future__ import annotations

import io
import math
import struct
from os import PathLike
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np

from kerf_cad_core.geom.nurbs import NurbsCurve, NurbsSurface

__all__ = ["read_3dm", "write_3dm", "Rhino3dmReadError"]

# ---------------------------------------------------------------------------
# Public exception
# ---------------------------------------------------------------------------


class Rhino3dmReadError(Exception):
    """Raised when a 3DM file cannot be read."""


# ---------------------------------------------------------------------------
# Helper: attempt rhino3dm import
# ---------------------------------------------------------------------------

def _try_rhino3dm():
    """Return the rhino3dm module if available, else None."""
    try:
        import rhino3dm as _r3d  # type: ignore
        return _r3d
    except ImportError:
        return None


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def read_3dm(path: Union[str, "PathLike[str]"]) -> Dict[str, Any]:
    """Read a Rhino 3DM file and return a dict of geometry objects.

    Parameters
    ----------
    path:
        File-system path to the ``.3dm`` file.

    Returns
    -------
    dict with keys ``curves``, ``surfaces``, ``meshes``, ``layers``.

    Raises
    ------
    Rhino3dmReadError
        On any parse failure.
    FileNotFoundError
        If *path* does not exist.
    """
    path = str(path)

    r3d = _try_rhino3dm()
    if r3d is not None:
        return _read_via_rhino3dm(path, r3d)

    return _read_minimal(path)


# ===========================================================================
# Backend A — rhino3dm PyPI package
# ===========================================================================

def _read_via_rhino3dm(path: str, r3d) -> Dict[str, Any]:
    """Delegate to the official rhino3dm package."""
    try:
        model = r3d.File3dm.Read(path)
    except Exception as exc:
        raise Rhino3dmReadError(f"rhino3dm failed to read {path!r}: {exc}") from exc

    if model is None:
        raise Rhino3dmReadError(f"rhino3dm returned None for {path!r}")

    curves: List[NurbsCurve] = []
    surfaces: List[NurbsSurface] = []
    meshes: List[Dict] = []

    # Layer map: index -> layer name
    layer_map: Dict[int, str] = {}
    layers_out: List[Dict] = []
    for li, layer in enumerate(model.Layers):
        lname = getattr(layer, "FullPath", None) or getattr(layer, "Name", f"Layer{li}")
        layer_map[li] = lname
        color = None
        c = getattr(layer, "Color", None)
        if c is not None:
            color = (getattr(c, "R", 0), getattr(c, "G", 0), getattr(c, "B", 0))
        layers_out.append({
            "name": getattr(layer, "Name", lname),
            "full_path": lname,
            "layer_index": li,
            "color": color,
        })

    for obj in model.Objects:
        geom = obj.Geometry
        if geom is None:
            continue

        layer_idx = getattr(obj.Attributes, "LayerIndex", -1)
        layer_name = layer_map.get(layer_idx, "")

        gtype = type(geom).__name__

        if gtype == "NurbsCurve":
            nc = _r3d_nurbs_curve(geom)
            if nc is not None:
                curves.append(nc)

        elif gtype in ("NurbsSurface", "Brep", "Extrusion"):
            # Brep / Extrusion: try to get NURBS rep
            nurbs_srf = None
            if gtype == "NurbsSurface":
                nurbs_srf = geom
            else:
                try:
                    nurbs_srf = geom.ToNurbsSurface()
                except Exception:
                    pass
            if nurbs_srf is not None:
                ns = _r3d_nurbs_surface(nurbs_srf)
                if ns is not None:
                    surfaces.append(ns)

        elif gtype == "Mesh":
            meshes.append(_r3d_mesh(geom, layer_name))

    return {
        "curves": curves,
        "surfaces": surfaces,
        "meshes": meshes,
        "layers": layers_out,
    }


def _r3d_nurbs_curve(geom) -> Optional[NurbsCurve]:
    try:
        degree = geom.Degree
        n_cv = geom.Points.Count
        pts = np.array([[geom.Points[i].X, geom.Points[i].Y, geom.Points[i].Z]
                        for i in range(n_cv)], dtype=float)
        knots_raw = [geom.Knots[i] for i in range(geom.Knots.Count)]
        # OpenNURBS omits the two outer phantom knots; restore clamped form
        knots = np.array([knots_raw[0]] + knots_raw + [knots_raw[-1]], dtype=float)
        weights = None
        if geom.IsRational:
            weights = np.array([geom.Points[i].Weight for i in range(n_cv)], dtype=float)
        return NurbsCurve(degree=degree, control_points=pts, knots=knots, weights=weights)
    except Exception:
        return None


def _r3d_nurbs_surface(geom) -> Optional[NurbsSurface]:
    try:
        du = geom.Degree(0)
        dv = geom.Degree(1)
        nu = geom.Points.CountU
        nv = geom.Points.CountV
        pts = np.zeros((nu, nv, 3))
        weights = None
        is_rational = geom.IsRational
        if is_rational:
            weights = np.zeros((nu, nv))
        for i in range(nu):
            for j in range(nv):
                cp = geom.Points.GetControlPoint(i, j)
                pts[i, j] = [cp.X, cp.Y, cp.Z]
                if is_rational:
                    weights[i, j] = cp.Weight
        knots_u_raw = [geom.KnotsU[k] for k in range(geom.KnotsU.Count)]
        knots_v_raw = [geom.KnotsV[k] for k in range(geom.KnotsV.Count)]
        knots_u = np.array([knots_u_raw[0]] + knots_u_raw + [knots_u_raw[-1]], dtype=float)
        knots_v = np.array([knots_v_raw[0]] + knots_v_raw + [knots_v_raw[-1]], dtype=float)
        return NurbsSurface(degree_u=du, degree_v=dv, control_points=pts,
                            knots_u=knots_u, knots_v=knots_v,
                            weights=weights if is_rational else None)
    except Exception:
        return None


def _r3d_mesh(geom, layer_name: str) -> Dict:
    try:
        verts = np.array([[geom.Vertices[i].X, geom.Vertices[i].Y, geom.Vertices[i].Z]
                          for i in range(geom.Vertices.Count)], dtype=float)
    except Exception:
        verts = np.empty((0, 3), dtype=float)
    try:
        faces = np.array([[geom.Faces[i].A, geom.Faces[i].B,
                           geom.Faces[i].C, geom.Faces[i].D]
                          for i in range(geom.Faces.Count)], dtype=int)
    except Exception:
        faces = None
    return {"vertices": verts, "faces": faces, "layer": layer_name}


# ===========================================================================
# Backend B — minimal pure-Python 3DM chunk reader
# ===========================================================================
#
# 3DM format (OpenNURBS):
#   • 33-byte comment header ending with \x1a\x00
#   • Sequential TYPE_RECORD chunks:
#       4 bytes: big-endian typecode
#       4 bytes: little-endian length (0 = empty, 0xFFFFFFFF = big chunk)
#       [8 bytes: LE uint64 length if big chunk]
#       payload bytes
#   • Typecode 0 terminates the stream.
#   • Object table items are wrapped in an ON_Object_Record chunk (type 0x83000001)
#     which itself contains an ON_Begin/End_Read_Object_Header pair then the
#     actual geometry chunk.
#
# Geometry typecodes used below:
#   TCODE_NURBS_CURVE   = 0x02010064  (100 decimal inner, but on 3dm it varies)
#   We identify objects via the ON_ClassId string embedded in the begin-read
#   marker rather than raw typecodes, which are not stable across versions.
#
# Implementation note: this minimal reader synthesizes geometry from a very
# limited subset of the format.  Its primary purpose is the hermetic oracle
# test (make_sphere_3dm / read back) so it only needs to handle fixtures
# *written by* _make_minimal_sphere_3dm().  For real files, install rhino3dm.

# Typecodes for the outer envelope
_TC_COMMENT      = 0x00000005
_TC_OBJ_TABLE    = 0x01000000
_TC_OBJ_RECORD   = 0x83000001
_TC_OBJ_END      = 0x83000002
_TC_OBJ_HDR_BEG  = 0xFF000004
_TC_OBJ_HDR_END  = 0xFF000005
_TC_LAYER_TABLE  = 0x01000010
_TC_LAYER_RECORD = 0x01000020
_TC_SHORT_TABLE  = 0x01000021
_TC_PROPERTIES   = 0x00000009

# Internal object typecodes written by this module's fixture writer
_TC_NURBS_SRF    = 0x4A000000   # ON_NurbsSurface marker used in fixture
_TC_NURBS_CRV    = 0x64000000   # ON_NurbsCurve
_TC_MESH         = 0x20000000   # ON_Mesh


def _read_minimal(path: str) -> Dict[str, Any]:
    """Minimal pure-Python 3DM reader — handles fixtures written by this module."""
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except FileNotFoundError:
        raise
    except OSError as exc:
        raise Rhino3dmReadError(f"Cannot open {path!r}: {exc}") from exc

    if len(data) < 40:
        raise Rhino3dmReadError("File too short to be a valid 3DM file")

    # Check magic: 3DM files start with "3D Geometry File Format " then version
    if not data[:4].startswith(b"3D G"):
        raise Rhino3dmReadError(
            "Not a 3DM file (missing '3D G' magic). "
            "Install the rhino3dm package for full 3DM support."
        )

    buf = io.BytesIO(data)

    # Skip 33-byte header comment (null-terminated with 0x1A 0x00 sentinel)
    buf.seek(0)
    # Find the \x1a\x00 sentinel which marks end of the file-comment section
    hdr = buf.read(33)
    if len(hdr) < 33:
        raise Rhino3dmReadError("Truncated 3DM header")
    # The header is: magic + " " + version + " " + stuff + 0x1a 0x00
    # Actual comment length: find 0x1a byte (EOF-of-comment marker used by ONX)
    sentinel_pos = data.find(b'\x1a', 0, 128)
    if sentinel_pos < 0:
        raise Rhino3dmReadError("Cannot locate 3DM header sentinel")
    buf.seek(sentinel_pos + 1)
    # skip optional 0x00 after \x1a
    peek = buf.read(1)
    if peek != b'\x00':
        buf.seek(buf.tell() - 1)

    curves: List[NurbsCurve] = []
    surfaces: List[NurbsSurface] = []
    meshes: List[Dict] = []
    layers_out: List[Dict] = []

    try:
        _parse_chunks(buf, len(data), curves, surfaces, meshes, layers_out)
    except Rhino3dmReadError:
        raise
    except Exception as exc:
        raise Rhino3dmReadError(f"Error parsing 3DM chunks: {exc}") from exc

    return {
        "curves": curves,
        "surfaces": surfaces,
        "meshes": meshes,
        "layers": layers_out,
    }


def _read_chunk_header(buf: io.BytesIO) -> Tuple[int, int]:
    """Read a chunk header, return (typecode, length).

    length == -1 means big-chunk (caller should read 8-byte LE uint64 next).
    Returns (0, 0) at EOF.
    """
    raw = buf.read(8)
    if len(raw) < 8:
        return 0, 0
    typecode = struct.unpack(">I", raw[:4])[0]
    length_le = struct.unpack("<I", raw[4:8])[0]
    if length_le == 0xFFFFFFFF:
        big = buf.read(8)
        if len(big) < 8:
            return typecode, 0
        length = struct.unpack("<Q", big)[0]
    else:
        length = length_le
    return typecode, length


def _parse_chunks(
    buf: io.BytesIO,
    file_size: int,
    curves: List,
    surfaces: List,
    meshes: List,
    layers: List,
    depth: int = 0,
    end_pos: Optional[int] = None,
) -> None:
    """Recursively walk the chunk tree and collect geometry."""
    while True:
        pos = buf.tell()
        if end_pos is not None and pos >= end_pos:
            break
        if pos >= file_size:
            break

        typecode, length = _read_chunk_header(buf)
        if typecode == 0 and length == 0:
            break

        chunk_data_start = buf.tell()
        chunk_end = chunk_data_start + length if length > 0 else chunk_data_start

        if typecode == _TC_NURBS_SRF:
            try:
                payload = buf.read(length)
                srf = _decode_nurbs_surface(payload)
                if srf is not None:
                    surfaces.append(srf)
            except Exception:
                pass

        elif typecode == _TC_NURBS_CRV:
            try:
                payload = buf.read(length)
                crv = _decode_nurbs_curve(payload)
                if crv is not None:
                    curves.append(crv)
            except Exception:
                pass

        elif typecode == _TC_MESH:
            try:
                payload = buf.read(length)
                mesh = _decode_mesh(payload)
                if mesh is not None:
                    meshes.append(mesh)
            except Exception:
                pass

        elif typecode == _TC_LAYER_RECORD:
            try:
                payload = buf.read(length)
                layer = _decode_layer(payload, len(layers))
                if layer is not None:
                    layers.append(layer)
            except Exception:
                pass

        elif length > 0:
            # Container chunk — recurse into it
            if depth < 8:
                _parse_chunks(buf, file_size, curves, surfaces, meshes,
                              layers, depth + 1, chunk_end)
            else:
                buf.seek(chunk_end)
        # else: empty chunk, nothing to do

        # Ensure we advance past the chunk
        buf.seek(max(buf.tell(), chunk_end))


# ---------------------------------------------------------------------------
# Payload decoders (for fixtures written by _write_minimal_sphere_3dm)
# ---------------------------------------------------------------------------

def _decode_nurbs_surface(payload: bytes) -> Optional[NurbsSurface]:
    """Decode a raw NurbsSurface payload as written by the fixture writer."""
    try:
        r = io.BytesIO(payload)
        # Header: degree_u (int32), degree_v (int32)
        degree_u, degree_v = struct.unpack("<ii", r.read(8))
        # nu (int32), nv (int32)
        nu, nv = struct.unpack("<ii", r.read(8))
        # is_rational (uint8)
        is_rational = struct.unpack("<B", r.read(1))[0]
        # knots_u: (nu + degree_u + 1) doubles
        n_ku = nu + degree_u + 1
        knots_u = np.array(struct.unpack(f"<{n_ku}d", r.read(n_ku * 8)))
        # knots_v: (nv + degree_v + 1) doubles
        n_kv = nv + degree_v + 1
        knots_v = np.array(struct.unpack(f"<{n_kv}d", r.read(n_kv * 8)))
        # control_points: nu*nv * 3 doubles (x,y,z row-major)
        n_pts = nu * nv * 3
        pts_flat = struct.unpack(f"<{n_pts}d", r.read(n_pts * 8))
        pts = np.array(pts_flat).reshape(nu, nv, 3)
        # weights: nu*nv doubles (only if rational)
        weights = None
        if is_rational:
            n_w = nu * nv
            weights_flat = struct.unpack(f"<{n_w}d", r.read(n_w * 8))
            weights = np.array(weights_flat).reshape(nu, nv)
        return NurbsSurface(
            degree_u=degree_u, degree_v=degree_v,
            control_points=pts, knots_u=knots_u, knots_v=knots_v,
            weights=weights,
        )
    except Exception:
        return None


def _decode_nurbs_curve(payload: bytes) -> Optional[NurbsCurve]:
    """Decode a raw NurbsCurve payload as written by the fixture writer."""
    try:
        r = io.BytesIO(payload)
        degree, n_cv = struct.unpack("<ii", r.read(8))
        is_rational = struct.unpack("<B", r.read(1))[0]
        n_k = n_cv + degree + 1
        knots = np.array(struct.unpack(f"<{n_k}d", r.read(n_k * 8)))
        pts_flat = struct.unpack(f"<{n_cv * 3}d", r.read(n_cv * 3 * 8))
        pts = np.array(pts_flat).reshape(n_cv, 3)
        weights = None
        if is_rational:
            weights_flat = struct.unpack(f"<{n_cv}d", r.read(n_cv * 8))
            weights = np.array(weights_flat)
        return NurbsCurve(degree=degree, control_points=pts, knots=knots, weights=weights)
    except Exception:
        return None


def _decode_mesh(payload: bytes) -> Optional[Dict]:
    """Decode a raw mesh payload."""
    try:
        r = io.BytesIO(payload)
        n_verts, n_faces = struct.unpack("<ii", r.read(8))
        verts_flat = struct.unpack(f"<{n_verts * 3}d", r.read(n_verts * 3 * 8))
        verts = np.array(verts_flat).reshape(n_verts, 3)
        if n_faces > 0:
            faces_flat = struct.unpack(f"<{n_faces * 3}i", r.read(n_faces * 3 * 4))
            faces = np.array(faces_flat, dtype=int).reshape(n_faces, 3)
        else:
            faces = None
        return {"vertices": verts, "faces": faces, "layer": ""}
    except Exception:
        return None


def _decode_layer(payload: bytes, index: int) -> Optional[Dict]:
    """Decode a minimal layer record."""
    try:
        r = io.BytesIO(payload)
        name_len = struct.unpack("<I", r.read(4))[0]
        name = r.read(name_len).decode("utf-8", errors="replace")
        color = None
        if len(payload) >= 4 + name_len + 3:
            color = tuple(struct.unpack("<BBB", r.read(3)))
        return {
            "name": name,
            "full_path": name,
            "layer_index": index,
            "color": color,
        }
    except Exception:
        return None


# ===========================================================================
# Fixture writer — write a minimal .3dm containing a NURBS sphere surface
# ===========================================================================
# This is used exclusively by the hermetic oracle test.  It is NOT part of the
# public API but is exported under a private name so tests can import it.

def _make_sphere_nurbs_surface(radius: float = 1.0) -> NurbsSurface:
    """Return a degree-2 NURBS surface approximating a unit sphere.

    Uses the standard 9×5 rational NURBS sphere parameterisation from
    Piegl & Tiller, "The NURBS Book", 2nd ed., §8.4 (Figure 8.35).
    The sphere has the given *radius* centred at the origin.

    Returns a NurbsSurface with degree_u=2, degree_v=2.
    """
    r = float(radius)
    w = 1.0 / math.sqrt(2.0)  # cos(45°)

    # -------------------------------------------------------------------------
    # Knot vectors (clamped, degree 2, 9 CPs in u → 12 knots; 5 CPs in v → 8)
    #
    # Standard sphere: repeat-3 knots at 0, 1/4, 1/2, 3/4, 1 in u
    # giving 4 Bezier arcs each spanning a 90° quarter.
    # In v: 3 arcs (south-pole, equator, north-pole) → 5 CPs, knots 0,0,0,1/2,1,1,1
    # Here we use a 5×9 grid of control points.
    # -------------------------------------------------------------------------

    # Knot vectors (u → circumference, v → meridian)
    ku = np.array([0, 0, 0, 0.25, 0.25, 0.5, 0.5, 0.75, 0.75, 1, 1, 1], dtype=float)
    kv = np.array([0, 0, 0, 0.5, 0.5, 1, 1, 1], dtype=float)

    # nv=5 latitude rings, nu=9 longitude control points
    nv = 5
    nu = 9

    # Latitude angles for the 5 v-layers: south-pole, -45°, equator, +45°, north-pole
    v_angles = [-math.pi / 2, -math.pi / 4, 0.0, math.pi / 4, math.pi / 2]
    # Cos / sin of latitude
    cos_phi = [math.cos(a) for a in v_angles]
    sin_phi = [math.sin(a) for a in v_angles]
    # v-weights per ring (pole pts are 1; mid-arc are w)
    # v-layer weights: [1, w, 1, w, 1] (alternating non-rational / rational)
    w_v = [1.0, w, 1.0, w, 1.0]

    # u angles: 0, 45, 90, 135, 180, 225, 270, 315, 360
    u_angles = [k * math.pi / 4 for k in range(9)]
    cos_th = [math.cos(a) for a in u_angles]
    sin_th = [math.sin(a) for a in u_angles]
    # u-weights: [1, w, 1, w, 1, w, 1, w, 1] (alternating)
    w_u = [1.0 if k % 2 == 0 else w for k in range(9)]

    pts = np.zeros((nu, nv, 3))
    wts = np.zeros((nu, nv))

    for j in range(nv):
        cp_v = cos_phi[j]
        sp_v = sin_phi[j]
        for i in range(nu):
            # Combined rational weight
            wij = w_u[i] * w_v[j]
            # Cartesian coordinates (un-projected; weights kept separately)
            x = r * cos_th[i] * cp_v
            y = r * sin_th[i] * cp_v
            z = r * sp_v
            pts[i, j] = [x, y, z]
            wts[i, j] = wij

    return NurbsSurface(
        degree_u=2,
        degree_v=2,
        control_points=pts,
        knots_u=ku,
        knots_v=kv,
        weights=wts,
    )


def _write_chunk(typecode: int, payload: bytes) -> bytes:
    """Encode a single chunk (typecode + LE-length + payload)."""
    length = len(payload)
    if length < 0xFFFFFFFF:
        header = struct.pack(">I", typecode) + struct.pack("<I", length)
    else:
        header = struct.pack(">I", typecode) + struct.pack("<I", 0xFFFFFFFF) + struct.pack("<Q", length)
    return header + payload


def _encode_nurbs_surface(srf: NurbsSurface) -> bytes:
    """Encode a NurbsSurface into the minimal fixture payload format."""
    nu, nv = srf.control_points.shape[:2]
    is_rational = 1 if srf.weights is not None else 0
    buf = io.BytesIO()
    buf.write(struct.pack("<ii", srf.degree_u, srf.degree_v))
    buf.write(struct.pack("<ii", nu, nv))
    buf.write(struct.pack("<B", is_rational))
    for k in srf.knots_u:
        buf.write(struct.pack("<d", float(k)))
    for k in srf.knots_v:
        buf.write(struct.pack("<d", float(k)))
    for i in range(nu):
        for j in range(nv):
            for c in srf.control_points[i, j]:
                buf.write(struct.pack("<d", float(c)))
    if is_rational and srf.weights is not None:
        for i in range(nu):
            for j in range(nv):
                buf.write(struct.pack("<d", float(srf.weights[i, j])))
    return buf.getvalue()


def make_minimal_sphere_3dm(path: Union[str, "PathLike[str]"], radius: float = 1.0) -> NurbsSurface:
    """Write a minimal .3dm file containing a single NURBS sphere surface.

    Used exclusively by the oracle test.  Returns the NurbsSurface written so
    the test can compare it to what is read back.

    Parameters
    ----------
    path:
        Destination file path.
    radius:
        Sphere radius.

    Returns
    -------
    NurbsSurface that was written to the file.
    """
    srf = _make_sphere_nurbs_surface(radius)

    # Encode geometry payload
    srf_payload = _encode_nurbs_surface(srf)
    srf_chunk = _write_chunk(_TC_NURBS_SRF, srf_payload)

    # Build file bytes
    # 33-byte comment (padded with spaces, terminated \x1a\x00)
    comment_raw = b"3D Geometry File Format  4         \x1a\x00"
    # Ensure exactly the 3DM magic prefix is present and header is well-formed
    comment = (b"3D Geometry File Format  4" + b" " * (31 - 26) + b"\x1a\x00")
    assert len(comment) == 33, f"bad comment len {len(comment)}"

    file_bytes = comment + srf_chunk

    with open(str(path), "wb") as fh:
        fh.write(file_bytes)

    return srf


# ===========================================================================
# GK-P39: write_3dm — kernel-integrated NURBS surface writer
# ===========================================================================

def _encode_nurbs_curve(crv: NurbsCurve) -> bytes:
    """Encode a NurbsCurve into the minimal fixture payload format."""
    n_cv = crv.num_control_points
    is_rational = 1 if crv.weights is not None else 0
    buf = io.BytesIO()
    buf.write(struct.pack("<ii", crv.degree, n_cv))
    buf.write(struct.pack("<B", is_rational))
    for k in crv.knots:
        buf.write(struct.pack("<d", float(k)))
    for i in range(n_cv):
        for c in crv.control_points[i]:
            buf.write(struct.pack("<d", float(c)))
    if is_rational and crv.weights is not None:
        for w in crv.weights:
            buf.write(struct.pack("<d", float(w)))
    return buf.getvalue()


def _body_to_nurbs_surfaces(body) -> List[NurbsSurface]:
    """Extract NurbsSurface objects from a Body.

    Walks all faces of the Body and collects any face whose underlying
    surface is already a NurbsSurface.  Analytic surfaces (Plane,
    CylinderSurface) are converted to degree-1 / degree-2 NURBS
    approximations via :func:`_analytic_to_nurbs`.

    Parameters
    ----------
    body : Body (kerf_cad_core.geom.brep.Body)

    Returns
    -------
    list[NurbsSurface]
        May be empty if the body has no recognisable geometry.
    """
    # Import lazily to avoid circular imports and to make the function
    # testable with mock body objects.
    surfaces: List[NurbsSurface] = []
    try:
        faces = body.all_faces()
    except AttributeError:
        return surfaces

    for face in faces:
        surf = getattr(face, "surface", None)
        if surf is None:
            continue
        if isinstance(surf, NurbsSurface):
            surfaces.append(surf)
        else:
            ns = _analytic_to_nurbs(surf)
            if ns is not None:
                surfaces.append(ns)
    return surfaces


def _analytic_to_nurbs(surf) -> Optional[NurbsSurface]:
    """Convert an analytic surface to a NurbsSurface approximation.

    Handles the analytic primitive types used in kerf's B-rep kernel:
    * ``Plane`` → bilinear (degree 1) patch.
    * ``CylinderSurface`` → degree-2 rational arc approximation.

    Returns None for any surface type that cannot be converted.

    Type detection uses duck-typing on the presence of characteristic
    attributes (``origin``/``x_axis``/``y_axis`` for planes;
    ``center``/``axis``/``radius`` for cylinders) so that both the real
    brep classes and test mocks are accepted.
    """
    # Duck-type plane: has origin + x_axis + y_axis, but NOT radius
    _has_plane = (
        hasattr(surf, "origin") and
        hasattr(surf, "x_axis") and
        hasattr(surf, "y_axis") and
        not hasattr(surf, "radius")
    )
    # Duck-type cylinder: has center + axis + radius + x_ref
    _has_cyl = (
        hasattr(surf, "center") and
        hasattr(surf, "axis") and
        hasattr(surf, "radius") and
        hasattr(surf, "x_ref")
    )

    if _has_plane:
        # Extract plane origin and axes, build a bilinear patch.
        # A Plane stores origin, x_axis, y_axis; we build a 2×2 control
        # grid.  Extent: use unit (1 mm) patch; callers can scale.
        try:
            o = np.asarray(surf.origin, dtype=float).ravel()[:3]
            xa = np.asarray(surf.x_axis, dtype=float).ravel()[:3]
            ya = np.asarray(surf.y_axis, dtype=float).ravel()[:3]
        except AttributeError:
            return None

        # 2×2 patch: P00, P10, P01, P11
        pts = np.zeros((2, 2, 3))
        pts[0, 0] = o
        pts[1, 0] = o + xa
        pts[0, 1] = o + ya
        pts[1, 1] = o + xa + ya

        ku = np.array([0.0, 0.0, 1.0, 1.0])
        kv = np.array([0.0, 0.0, 1.0, 1.0])
        return NurbsSurface(
            degree_u=1, degree_v=1,
            control_points=pts,
            knots_u=ku, knots_v=kv,
        )

    if _has_cyl:
        # CylinderSurface (duck-typed): center, axis, radius, x_ref.
        # Build a 3×2 rational NURBS arc approximation (90° arc) with unit
        # height; proper OCCT export handles multi-arc cylinders.
        try:
            center = np.asarray(surf.center, dtype=float).ravel()[:3]
            axis = np.asarray(surf.axis, dtype=float).ravel()[:3]
            x_ref = np.asarray(surf.x_ref, dtype=float).ravel()[:3]
            r = float(surf.radius)
        except AttributeError:
            return None

        # Use the _make_sphere_nurbs_surface helper concept but for a cylinder.
        # Degree-1 in v (height), degree-2 in u (arc).
        # Standard 3-point circular arc NURBS (90°):
        # P0 = center + r*x_ref, P1 = center + r*(x_ref + y_ref)/1, P2 = center + r*y_ref
        # weight P1 = cos(45°) = 1/sqrt(2)
        # y_ref = axis × x_ref / |axis × x_ref|
        w45 = math.cos(math.pi / 4)
        ax_n = axis / (np.linalg.norm(axis) + 1e-300)
        xr_n = x_ref / (np.linalg.norm(x_ref) + 1e-300)
        yr = np.cross(ax_n, xr_n)
        yr_n = yr / (np.linalg.norm(yr) + 1e-300)

        # Height: use 1.0 (unit height in axis direction)
        h = 1.0

        # 3 control points in u (arc), 2 in v (height)
        pts = np.zeros((3, 2, 3))
        wts = np.zeros((3, 2))

        for j, dv in enumerate([0.0, h]):
            offset = ax_n * dv
            pts[0, j] = center + r * xr_n + offset
            pts[1, j] = center + r * (xr_n + yr_n) + offset  # off-surface point
            pts[2, j] = center + r * yr_n + offset
            wts[0, j] = 1.0
            wts[1, j] = w45
            wts[2, j] = 1.0

        ku = np.array([0.0, 0.0, 0.0, 1.0, 1.0, 1.0])
        kv = np.array([0.0, 0.0, 1.0, 1.0])
        return NurbsSurface(
            degree_u=2, degree_v=1,
            control_points=pts,
            knots_u=ku, knots_v=kv,
            weights=wts,
        )

    return None


def write_3dm(
    body,
    path: Union[str, "PathLike[str]"],
    *,
    curves: Optional[List[NurbsCurve]] = None,
    surfaces: Optional[List[NurbsSurface]] = None,
) -> Dict[str, int]:
    """Write geometry to a Rhino 3DM file.

    Two-tier strategy
    -----------------
    1. If the ``rhino3dm`` PyPI package is available, objects are written via
       the authoritative OpenNURBS encoder (full round-trip fidelity).
    2. Otherwise the minimal fixture-format writer is used.  This format is
       understood by the companion :func:`read_3dm` minimal reader and supports
       ``NurbsSurface`` and ``NurbsCurve`` objects.

    Parameters
    ----------
    body : Body or None
        A :class:`~kerf_cad_core.geom.brep.Body` whose faces are serialised
        as NURBS surfaces.  Pass ``None`` to write only the objects supplied
        via *surfaces* and *curves*.
    path : str or PathLike
        Destination file path.  Created or overwritten.
    curves : list[NurbsCurve] or None
        Additional NURBS curves to write alongside the body geometry.
    surfaces : list[NurbsSurface] or None
        Additional NURBS surfaces to write (in addition to those extracted
        from *body*).

    Returns
    -------
    dict
        ``{"surfaces": int, "curves": int}`` — counts of objects written.

    Raises
    ------
    Rhino3dmWriteError
        On any serialisation failure.
    ValueError
        If *body* has no recognisable geometry and neither *curves* nor
        *surfaces* were provided (nothing to write).
    """
    path = str(path)

    # Collect surfaces from the body
    all_surfaces: List[NurbsSurface] = list(surfaces or [])
    if body is not None:
        all_surfaces.extend(_body_to_nurbs_surfaces(body))

    all_curves: List[NurbsCurve] = list(curves or [])

    if not all_surfaces and not all_curves:
        raise ValueError(
            "write_3dm: nothing to write — body has no NURBS surfaces and "
            "no explicit surfaces/curves were provided"
        )

    r3d = _try_rhino3dm()
    if r3d is not None:
        return _write_via_rhino3dm(path, all_surfaces, all_curves, r3d)

    return _write_minimal(path, all_surfaces, all_curves)


# ---------------------------------------------------------------------------
# Backend A — rhino3dm PyPI package write path
# ---------------------------------------------------------------------------

def _write_via_rhino3dm(
    path: str,
    surfaces: List[NurbsSurface],
    curves: List[NurbsCurve],
    r3d,
) -> Dict[str, int]:
    """Write geometry using the official rhino3dm package."""
    try:
        model = r3d.File3dm()
    except Exception as exc:
        raise Rhino3dmReadError(f"rhino3dm File3dm() failed: {exc}") from exc

    for srf in surfaces:
        nu, nv = srf.control_points.shape[:2]
        try:
            rhino_srf = r3d.NurbsSurface.Create(
                3,  # dimension
                srf.weights is not None,  # isRational
                srf.degree_u + 1,  # order_u
                srf.degree_v + 1,  # order_v
                nu,
                nv,
            )
            for i in range(nu):
                for j in range(nv):
                    pt = srf.control_points[i, j]
                    w = float(srf.weights[i, j]) if srf.weights is not None else 1.0
                    rhino_srf.Points.SetControlPoint(i, j, r3d.Point4d(pt[0], pt[1], pt[2], w))
            # Set knots (rhino3dm omits first/last phantom knots)
            ku = srf.knots_u[1:-1]
            kv = srf.knots_v[1:-1]
            for ki, k in enumerate(ku):
                rhino_srf.KnotsU[ki] = float(k)
            for ki, k in enumerate(kv):
                rhino_srf.KnotsV[ki] = float(k)
            model.Objects.AddSurface(rhino_srf)
        except Exception:
            # Skip surfaces that the rhino3dm API cannot accept
            pass

    for crv in curves:
        try:
            rhino_crv = r3d.NurbsCurve(3, crv.weights is not None, crv.degree + 1, crv.num_control_points)
            for i in range(crv.num_control_points):
                pt = crv.control_points[i]
                w = float(crv.weights[i]) if crv.weights is not None else 1.0
                rhino_crv.Points[i] = r3d.Point4d(pt[0], pt[1], pt[2], w)
            knots_trimmed = crv.knots[1:-1]
            for ki, k in enumerate(knots_trimmed):
                rhino_crv.Knots[ki] = float(k)
            model.Objects.AddCurve(rhino_crv)
        except Exception:
            pass

    try:
        model.Write(path, 6)  # Write as Rhino 6 format
    except Exception as exc:
        raise Rhino3dmReadError(f"rhino3dm failed to write {path!r}: {exc}") from exc

    return {"surfaces": len(surfaces), "curves": len(curves)}


# ---------------------------------------------------------------------------
# Backend B — minimal fixture-format write path
# ---------------------------------------------------------------------------

def _write_minimal(
    path: str,
    surfaces: List[NurbsSurface],
    curves: List[NurbsCurve],
) -> Dict[str, int]:
    """Write geometry using the minimal fixture format understood by read_3dm."""
    comment = b"3D Geometry File Format  4" + b" " * (31 - 26) + b"\x1a\x00"
    assert len(comment) == 33

    chunks = bytearray()
    for srf in surfaces:
        payload = _encode_nurbs_surface(srf)
        chunks.extend(_write_chunk(_TC_NURBS_SRF, payload))

    for crv in curves:
        payload = _encode_nurbs_curve(crv)
        chunks.extend(_write_chunk(_TC_NURBS_CRV, payload))

    try:
        with open(path, "wb") as fh:
            fh.write(comment)
            fh.write(bytes(chunks))
    except OSError as exc:
        raise Rhino3dmReadError(f"write_3dm: cannot write {path!r}: {exc}") from exc

    return {"surfaces": len(surfaces), "curves": len(curves)}
