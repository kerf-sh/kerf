"""
kerf_dental.dicom_ingest — DICOM-to-mesh ingest.

Public API
----------
DicomIngestResult
    Holds mesh vertices and faces, plus DICOM metadata.

ingest_dicom(path_or_bytes, *, iso_value=300) -> DicomIngestResult
    Load a DICOM file (or bytes) and extract a surface mesh via marching
    cubes at *iso_value* (Hounsfield units, default 300 = approximate
    bone/enamel boundary).

ingest_dicom_series(paths, *, iso_value=300) -> DicomIngestResult
    Load a series of axial DICOM slices (sorted by z-position) and
    extract a combined mesh.

AVAILABILITY
------------
This module degrades gracefully when *pydicom* is absent:

    from kerf_dental.dicom_ingest import PYDICOM_AVAILABLE
    if not PYDICOM_AVAILABLE:
        # DICOM ingest is disabled; advise user to install pydicom.
        ...

When pydicom is absent, calling ingest_dicom() / ingest_dicom_series()
raises DicomUnavailableError (a subclass of ImportError) with a clear
install hint, rather than a bare ImportError.

MARCHING CUBES
--------------
The marching-cubes algorithm is provided by scipy.ndimage / skimage if
available.  We ship a minimal pure-NumPy fallback for cube-march on 2×2×2
voxel neighbourhoods so the module is always exercisable.  The fallback is
for testing only; install scikit-image for production-grade meshes.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from typing import Sequence

import numpy as np


# ---------------------------------------------------------------------------
# Optional dependency detection
# ---------------------------------------------------------------------------

PYDICOM_AVAILABLE: bool = False
try:
    import pydicom  # noqa: F401
    PYDICOM_AVAILABLE = True
except ImportError:
    pass

_SKIMAGE_AVAILABLE: bool = False
try:
    from skimage.measure import marching_cubes as _ski_marching_cubes  # noqa: F401
    _SKIMAGE_AVAILABLE = True
except ImportError:
    pass


class DicomUnavailableError(ImportError):
    """Raised when pydicom is not installed."""


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class DicomIngestResult:
    """Surface mesh extracted from DICOM volume data."""

    vertices: np.ndarray
    """(N, 3) float32 — vertex coordinates in mm."""

    faces: np.ndarray
    """(M, 3) int32 — triangle face indices into vertices."""

    metadata: dict = field(default_factory=dict)
    """DICOM metadata: patient, modality, voxel spacing, etc.  Empty when
    pydicom is absent but marching cubes runs on synthetic data."""

    iso_value: float = 300.0
    """Hounsfield threshold used for surface extraction."""

    @property
    def vertex_count(self) -> int:
        return len(self.vertices)

    @property
    def face_count(self) -> int:
        return len(self.faces)


# ---------------------------------------------------------------------------
# Minimal marching-cubes fallback (pure NumPy, 2×2×2 window)
# ---------------------------------------------------------------------------

def _march_cubes_numpy(
    volume: np.ndarray,
    iso: float,
    spacing: tuple[float, float, float] = (1.0, 1.0, 1.0),
) -> tuple[np.ndarray, np.ndarray]:
    """
    Minimal marching-cubes surface extraction.

    For each 2×2×2 voxel cube, split the cube into 5 tetrahedra and
    extract triangle(s) at the iso-surface using linear interpolation.

    Parameters
    ----------
    volume  : (Z, Y, X) float32 voxel array
    iso     : iso-surface value
    spacing : (dz, dy, dx) voxel size in mm

    Returns
    -------
    vertices : (N, 3) float32  — world-space coordinates (z*dz, y*dy, x*dx)
    faces    : (M, 3) int32    — triangle vertex indices
    """
    dz, dy, dx = spacing
    Z, Y, X = volume.shape
    verts: list[np.ndarray] = []
    tris: list[tuple[int, int, int]] = []

    def _lerp(p0: np.ndarray, v0: float, p1: np.ndarray, v1: float) -> np.ndarray:
        t = (iso - v0) / (v1 - v0 + 1e-30)
        return p0 + t * (p1 - p0)

    vert_idx: dict[tuple, int] = {}

    def _get_or_add(pt: np.ndarray) -> int:
        key = (round(float(pt[0]), 5), round(float(pt[1]), 5), round(float(pt[2]), 5))
        if key not in vert_idx:
            vert_idx[key] = len(verts)
            verts.append(pt.astype(np.float32))
        return vert_idx[key]

    # Tetrahedral decomposition of a unit cube (5 tetrahedra)
    # Each tet: 4 vertex indices into the 8 cube corners
    # Corners: (iz, iy, ix) offsets 0/1
    _TETS = [
        (0, 1, 3, 5),
        (1, 3, 5, 7),
        (0, 3, 4, 5),
        (3, 4, 5, 6),
        (3, 5, 6, 7),
    ]

    for iz in range(Z - 1):
        for iy in range(Y - 1):
            for ix in range(X - 1):
                # 8 cube corners (bit: z*4 + y*2 + x*1)
                coords = np.array([
                    [iz * dz, iy * dy, ix * dx],
                    [iz * dz, iy * dy, (ix + 1) * dx],
                    [iz * dz, (iy + 1) * dy, ix * dx],
                    [iz * dz, (iy + 1) * dy, (ix + 1) * dx],
                    [(iz + 1) * dz, iy * dy, ix * dx],
                    [(iz + 1) * dz, iy * dy, (ix + 1) * dx],
                    [(iz + 1) * dz, (iy + 1) * dy, ix * dx],
                    [(iz + 1) * dz, (iy + 1) * dy, (ix + 1) * dx],
                ], dtype=np.float32)
                values = np.array([
                    volume[iz, iy, ix],
                    volume[iz, iy, ix + 1],
                    volume[iz, iy + 1, ix],
                    volume[iz, iy + 1, ix + 1],
                    volume[iz + 1, iy, ix],
                    volume[iz + 1, iy, ix + 1],
                    volume[iz + 1, iy + 1, ix],
                    volume[iz + 1, iy + 1, ix + 1],
                ], dtype=float)

                for tet in _TETS:
                    tc = [coords[i] for i in tet]
                    tv = [values[i] for i in tet]
                    above = [v >= iso for v in tv]
                    n_above = sum(above)
                    if n_above == 0 or n_above == 4:
                        continue

                    # Crossing edges
                    crossing: list[np.ndarray] = []
                    edges = [(0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)]
                    for a, b in edges:
                        if above[a] != above[b]:
                            pt = _lerp(tc[a], tv[a], tc[b], tv[b])
                            crossing.append(pt)

                    # For a tetrahedron, n_above in {1,2,3} gives 3 or 4 crossings
                    if len(crossing) == 3:
                        idx = [_get_or_add(p) for p in crossing]
                        tris.append((idx[0], idx[1], idx[2]))
                    elif len(crossing) == 4:
                        idx = [_get_or_add(p) for p in crossing]
                        tris.append((idx[0], idx[1], idx[2]))
                        tris.append((idx[0], idx[2], idx[3]))

    if not verts:
        return np.zeros((0, 3), dtype=np.float32), np.zeros((0, 3), dtype=np.int32)

    return (
        np.array(verts, dtype=np.float32),
        np.array(tris, dtype=np.int32),
    )


def _marching_cubes(
    volume: np.ndarray,
    iso: float,
    spacing: tuple[float, float, float],
) -> tuple[np.ndarray, np.ndarray]:
    """Dispatch to scikit-image (preferred) or pure-NumPy fallback."""
    if _SKIMAGE_AVAILABLE:
        from skimage.measure import marching_cubes as _ski_mc
        verts, faces, _, _ = _ski_mc(volume, level=iso, spacing=spacing)
        return verts.astype(np.float32), faces.astype(np.int32)
    return _march_cubes_numpy(volume, iso, spacing)


# ---------------------------------------------------------------------------
# DICOM volume loader
# ---------------------------------------------------------------------------

def _require_pydicom():
    if not PYDICOM_AVAILABLE:
        raise DicomUnavailableError(
            "pydicom is not installed. "
            "Install it with:  pip install pydicom\n"
            "or add the optional dependency:  pip install 'kerf-dental[dicom]'"
        )


def _load_pixel_array(ds) -> tuple[np.ndarray, dict]:
    """Extract pixel array and metadata from a pydicom Dataset."""
    import pydicom
    meta = {}
    for tag in ("Modality", "PatientName", "StudyDate", "SeriesDescription"):
        val = getattr(ds, tag, None)
        if val is not None:
            meta[tag] = str(val)
    spacing_xy = getattr(ds, "PixelSpacing", [1.0, 1.0])
    slice_thickness = float(getattr(ds, "SliceThickness", 1.0))
    meta["PixelSpacing"] = [float(s) for s in spacing_xy]
    meta["SliceThickness"] = slice_thickness
    meta["RescaleSlope"] = float(getattr(ds, "RescaleSlope", 1.0))
    meta["RescaleIntercept"] = float(getattr(ds, "RescaleIntercept", -1024.0))

    pixels = ds.pixel_array.astype(np.float32)
    pixels = pixels * meta["RescaleSlope"] + meta["RescaleIntercept"]
    return pixels, meta


def ingest_dicom(
    path_or_bytes,
    *,
    iso_value: float = 300.0,
) -> DicomIngestResult:
    """
    Load a single DICOM file and extract a surface mesh via marching cubes.

    Parameters
    ----------
    path_or_bytes : str | pathlib.Path | bytes
        DICOM file path or raw bytes.
    iso_value : float
        Hounsfield-unit threshold (default 300 — bone/enamel boundary).

    Returns
    -------
    DicomIngestResult

    Raises
    ------
    DicomUnavailableError  when pydicom is not installed.
    """
    _require_pydicom()
    import pydicom

    if isinstance(path_or_bytes, (bytes, bytearray)):
        ds = pydicom.dcmread(io.BytesIO(path_or_bytes))
    else:
        ds = pydicom.dcmread(str(path_or_bytes))

    pixels_2d, meta = _load_pixel_array(ds)
    # Treat as a single-slice volume (Z=1)
    volume = pixels_2d[np.newaxis, :, :]
    sy, sx = meta["PixelSpacing"]
    sz = meta["SliceThickness"]
    spacing = (float(sz), float(sy), float(sx))

    verts, faces = _marching_cubes(volume, iso_value, spacing)
    return DicomIngestResult(
        vertices=verts,
        faces=faces,
        metadata=meta,
        iso_value=iso_value,
    )


def ingest_dicom_series(
    paths: Sequence,
    *,
    iso_value: float = 300.0,
) -> DicomIngestResult:
    """
    Load an ordered series of axial DICOM slices and extract a 3-D mesh.

    Parameters
    ----------
    paths : sequence of str | pathlib.Path
        DICOM slice paths, sorted in ascending z-order (or will be sorted
        by ImagePositionPatient[2] when available).
    iso_value : float
        Hounsfield-unit threshold.

    Returns
    -------
    DicomIngestResult

    Raises
    ------
    DicomUnavailableError  when pydicom is not installed.
    ValueError             when paths is empty.
    """
    _require_pydicom()
    import pydicom

    path_list = list(paths)
    if not path_list:
        raise ValueError("paths must not be empty")

    datasets = [pydicom.dcmread(str(p)) for p in path_list]

    # Sort by ImagePositionPatient z if available
    def _z(ds):
        ipp = getattr(ds, "ImagePositionPatient", None)
        if ipp is not None:
            try:
                return float(ipp[2])
            except (IndexError, ValueError):
                pass
        return 0.0

    datasets.sort(key=_z)

    slices = []
    meta = {}
    for ds in datasets:
        sl, m = _load_pixel_array(ds)
        slices.append(sl)
        if not meta:
            meta = m

    volume = np.stack(slices, axis=0)  # (Z, Y, X)
    sy, sx = meta.get("PixelSpacing", [1.0, 1.0])
    sz = meta.get("SliceThickness", 1.0)
    spacing = (float(sz), float(sy), float(sx))

    verts, faces = _marching_cubes(volume, iso_value, spacing)
    return DicomIngestResult(
        vertices=verts,
        faces=faces,
        metadata=meta,
        iso_value=iso_value,
    )
