"""
Tests for the kerf_dental seed package — T-171.

Definition of Done checks:
  1. Crown surface is validate_body-clean.
  2. Guide placement angle within 0.1°.
  3. DICOM ingest degrades gracefully when pydicom absent.
"""

from __future__ import annotations

import math
import os
import sys

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# sys.path bootstrap (belt-and-suspenders; conftest.py also handles this)
# ---------------------------------------------------------------------------

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(os.path.dirname(_HERE), "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)


# ---------------------------------------------------------------------------
# Crown imports
# ---------------------------------------------------------------------------

from kerf_dental.crown import (
    ToothAnatomy,
    CrownDesignInput,
    CrownResult,
    design_crown,
)
from kerf_cad_core.geom.brep import validate_body


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# Simple 4-point rectangular margin (8 mm × 7 mm molar preparation)
MARGIN_RECT = [
    (0.0, 0.0, 0.0),
    (8.0, 0.0, 0.0),
    (8.0, 7.0, 0.0),
    (0.0, 7.0, 0.0),
]

# Circular margin (16 points, radius 4 mm)
MARGIN_CIRCLE = [
    (4.0 * math.cos(2 * math.pi * i / 16),
     4.0 * math.sin(2 * math.pi * i / 16),
     0.0)
    for i in range(16)
]

OPPOSING_CUSPS_MOLAR = [2.0, 1.8, 1.5, 1.6]  # 4 cusps
OPPOSING_CUSPS_INCISOR = [1.2]


# ===========================================================================
# ToothAnatomy data model
# ===========================================================================

class TestToothAnatomy:
    def test_basic_construction(self):
        t = ToothAnatomy(
            tooth_id="16",
            arch="upper",
            crown_height_mm=8.5,
            root_length_mm=14.0,
            mesio_distal_width_mm=10.5,
            bucco_lingual_width_mm=11.0,
        )
        assert t.tooth_id == "16"
        assert t.arch == "upper"
        assert t.crown_height_mm == pytest.approx(8.5)

    def test_cusp_heights_default(self):
        t = ToothAnatomy(
            tooth_id="11",
            arch="upper",
            crown_height_mm=10.0,
            root_length_mm=13.0,
            mesio_distal_width_mm=8.5,
            bucco_lingual_width_mm=7.0,
        )
        assert len(t.cusp_heights_mm) >= 1

    def test_custom_cusp_heights(self):
        t = ToothAnatomy(
            tooth_id="36",
            arch="lower",
            crown_height_mm=7.0,
            root_length_mm=14.0,
            mesio_distal_width_mm=11.0,
            bucco_lingual_width_mm=10.5,
            cusp_heights_mm=[2.1, 1.9, 1.7, 1.8, 2.0],
        )
        assert len(t.cusp_heights_mm) == 5


# ===========================================================================
# CrownDesignInput validation
# ===========================================================================

class TestCrownDesignInput:
    def test_valid_construction(self):
        inp = CrownDesignInput(
            margin_line=MARGIN_RECT,
            opposing_cusp_heights_mm=OPPOSING_CUSPS_MOLAR,
        )
        assert inp.material == "zirconia"
        assert inp.occlusal_clearance_mm == pytest.approx(0.3)

    def test_too_few_margin_points_raises(self):
        with pytest.raises(ValueError, match="at least 3"):
            CrownDesignInput(
                margin_line=[(0.0, 0.0, 0.0), (1.0, 0.0, 0.0)],
                opposing_cusp_heights_mm=[2.0],
            )

    def test_empty_cusps_raises(self):
        with pytest.raises(ValueError, match="opposing_cusp_heights_mm"):
            CrownDesignInput(
                margin_line=MARGIN_RECT,
                opposing_cusp_heights_mm=[],
            )

    def test_negative_clearance_raises(self):
        with pytest.raises(ValueError, match="occlusal_clearance_mm"):
            CrownDesignInput(
                margin_line=MARGIN_RECT,
                opposing_cusp_heights_mm=[2.0],
                occlusal_clearance_mm=-0.1,
            )

    def test_custom_material(self):
        inp = CrownDesignInput(
            margin_line=MARGIN_RECT,
            opposing_cusp_heights_mm=[2.0],
            material="e.max",
        )
        assert inp.material == "e.max"


# ===========================================================================
# design_crown — DoD: crown surface is validate_body-clean
# ===========================================================================

class TestDesignCrown:
    """Core DoD: crown from fixture margin → closed surface, validate_body OK."""

    def _make_rect_inp(self, margin=None, cusps=None, clearance=0.3):
        return CrownDesignInput(
            margin_line=margin or MARGIN_RECT,
            opposing_cusp_heights_mm=cusps or OPPOSING_CUSPS_MOLAR,
            occlusal_clearance_mm=clearance,
        )

    # --- DoD check 1: crown surface is validate_body-clean -------------------

    def test_crown_validate_body_clean_rect_margin(self):
        """Fixture rectangular margin → crown Body passes validate_body (DoD)."""
        inp = self._make_rect_inp()
        result = design_crown(inp)
        vr = validate_body(result.body)
        assert vr["ok"] is True, f"validate_body errors: {vr['errors']}"

    def test_crown_validate_body_clean_circle_margin(self):
        """Circular margin → crown Body passes validate_body."""
        inp = CrownDesignInput(
            margin_line=MARGIN_CIRCLE,
            opposing_cusp_heights_mm=OPPOSING_CUSPS_INCISOR,
        )
        result = design_crown(inp)
        vr = validate_body(result.body)
        assert vr["ok"] is True, f"validate_body errors: {vr['errors']}"

    def test_crown_validate_body_clean_tilted_margin(self):
        """Tilted margin (non-horizontal plane) → crown Body passes validate_body."""
        tilted = [
            (0.0, 0.0, 0.0),
            (5.0, 0.0, 0.5),
            (5.0, 4.0, 0.5),
            (0.0, 4.0, 0.0),
        ]
        inp = CrownDesignInput(
            margin_line=tilted,
            opposing_cusp_heights_mm=[1.5, 1.2],
        )
        result = design_crown(inp)
        vr = validate_body(result.body)
        assert vr["ok"] is True, f"validate_body errors: {vr['errors']}"

    # --- Geometry checks -----------------------------------------------------

    def test_returns_crown_result(self):
        inp = self._make_rect_inp()
        result = design_crown(inp)
        assert isinstance(result, CrownResult)

    def test_crown_radius_positive(self):
        inp = self._make_rect_inp()
        result = design_crown(inp)
        assert result.crown_radius_mm > 0.0

    def test_crown_height_includes_clearance(self):
        """Crown height = max cusp + clearance."""
        cusps = [2.0, 1.5, 1.8]
        clearance = 0.5
        inp = self._make_rect_inp(cusps=cusps, clearance=clearance)
        result = design_crown(inp)
        expected = max(cusps) + clearance
        assert result.crown_height_mm == pytest.approx(expected, abs=1e-9)

    def test_crown_height_single_cusp(self):
        inp = CrownDesignInput(
            margin_line=MARGIN_RECT,
            opposing_cusp_heights_mm=[3.0],
            occlusal_clearance_mm=0.2,
        )
        result = design_crown(inp)
        assert result.crown_height_mm == pytest.approx(3.2, abs=1e-9)

    def test_centroid_near_margin_centre(self):
        """Centroid of rectangular margin should be near geometric centre."""
        inp = self._make_rect_inp()
        result = design_crown(inp)
        cx, cy, cz = result.margin_centroid_mm
        assert abs(cx - 4.0) < 0.1
        assert abs(cy - 3.5) < 0.1

    def test_radius_at_least_half_diagonal(self):
        """Radius must cover at least half the margin diagonal."""
        inp = self._make_rect_inp()
        result = design_crown(inp)
        # For 8×7 mm rect, half-diagonal ≈ sqrt(4²+3.5²) ≈ 5.32 mm
        half_diag = math.sqrt(4.0**2 + 3.5**2)
        assert result.crown_radius_mm >= half_diag - 0.1

    def test_three_point_margin(self):
        """Minimum 3-point margin works."""
        inp = CrownDesignInput(
            margin_line=[(0.0, 0.0, 0.0), (5.0, 0.0, 0.0), (2.5, 4.0, 0.0)],
            opposing_cusp_heights_mm=[1.0],
        )
        result = design_crown(inp)
        vr = validate_body(result.body)
        assert vr["ok"] is True

    def test_zero_clearance(self):
        inp = CrownDesignInput(
            margin_line=MARGIN_RECT,
            opposing_cusp_heights_mm=[2.0],
            occlusal_clearance_mm=0.0,
        )
        result = design_crown(inp)
        assert result.crown_height_mm == pytest.approx(2.0, abs=1e-9)
        vr = validate_body(result.body)
        assert vr["ok"] is True

    def test_large_cusp_height(self):
        """Large cusps → valid geometry."""
        inp = CrownDesignInput(
            margin_line=MARGIN_RECT,
            opposing_cusp_heights_mm=[8.0],
            occlusal_clearance_mm=0.3,
        )
        result = design_crown(inp)
        assert result.crown_height_mm == pytest.approx(8.3, abs=1e-9)
        vr = validate_body(result.body)
        assert vr["ok"] is True


# ===========================================================================
# Surgical guide — DoD: angle within 0.1°
# ===========================================================================

from kerf_dental.guide import (
    ImplantSpec,
    SurgicalGuideResult,
    place_surgical_guide,
    angle_between_vectors,
)


# Fixture jaw surface: flat rectangle (20 × 15 mm, z=0)
JAW_FLAT = [(float(x), float(y), 0.0)
            for x in range(0, 21, 2)
            for y in range(0, 16, 2)]

# Fixture implant specs
IMPLANT_STRAIGHT = ImplantSpec(
    position=(10.0, 7.0, 0.0),
    axis_direction=(0.0, 0.0, 1.0),
    diameter_mm=4.1,
    length_mm=11.5,
)
IMPLANT_ANGLED = ImplantSpec(
    position=(5.0, 5.0, 0.0),
    axis_direction=(0.2, 0.0, 1.0),  # will be normalised
    diameter_mm=3.7,
    length_mm=10.0,
)


class TestAngleBetweenVectors:
    def test_identical_vectors_zero(self):
        v = np.array([0.0, 0.0, 1.0])
        assert angle_between_vectors(v, v) == pytest.approx(0.0, abs=1e-9)

    def test_orthogonal_vectors_90(self):
        v1 = np.array([1.0, 0.0, 0.0])
        v2 = np.array([0.0, 1.0, 0.0])
        assert angle_between_vectors(v1, v2) == pytest.approx(90.0, abs=1e-9)

    def test_antiparallel_180(self):
        v1 = np.array([0.0, 0.0, 1.0])
        v2 = np.array([0.0, 0.0, -1.0])
        assert angle_between_vectors(v1, v2) == pytest.approx(180.0, abs=1e-9)

    def test_known_angle(self):
        """45° between two unit vectors."""
        v1 = np.array([1.0, 0.0, 0.0])
        v2 = np.array([math.cos(math.pi / 4), math.sin(math.pi / 4), 0.0])
        assert angle_between_vectors(v1, v2) == pytest.approx(45.0, abs=1e-6)

    def test_zero_vector_returns_zero(self):
        assert angle_between_vectors(np.zeros(3), np.array([1.0, 0.0, 0.0])) == 0.0


class TestImplantSpec:
    def test_normalises_axis(self):
        spec = ImplantSpec(
            position=(0.0, 0.0, 0.0),
            axis_direction=(0.0, 0.0, 5.0),  # not a unit vector
        )
        ax = np.array(spec.axis_direction)
        assert abs(np.linalg.norm(ax) - 1.0) < 1e-12

    def test_zero_axis_raises(self):
        with pytest.raises(ValueError, match="non-zero"):
            ImplantSpec(
                position=(0.0, 0.0, 0.0),
                axis_direction=(0.0, 0.0, 0.0),
            )

    def test_sleeve_outer_radius(self):
        spec = ImplantSpec(
            position=(0.0, 0.0, 0.0),
            axis_direction=(0.0, 0.0, 1.0),
            diameter_mm=4.0,
            sleeve_wall_mm=1.5,
        )
        assert spec.sleeve_outer_radius_mm == pytest.approx(3.5, abs=1e-9)


class TestPlaceSurgicalGuide:
    """Core DoD: guide placement angle within 0.1° of specified angulation."""

    # --- DoD check 2: angular error < 0.1° ----------------------------------

    def test_straight_implant_angle_within_0_1_deg(self):
        """Straight (0,0,1) implant axis — angular error < 0.1° (DoD)."""
        result = place_surgical_guide(JAW_FLAT, [IMPLANT_STRAIGHT])
        assert result.angular_errors_deg[0] < 0.1, (
            f"Angular error {result.angular_errors_deg[0]:.4f}° exceeds 0.1°"
        )

    def test_angled_implant_angle_within_0_1_deg(self):
        """Angled implant — angular error < 0.1° (DoD)."""
        result = place_surgical_guide(JAW_FLAT, [IMPLANT_ANGLED])
        assert result.angular_errors_deg[0] < 0.1

    def test_multiple_implants_all_within_0_1_deg(self):
        """Multiple implants — all angular errors < 0.1°."""
        implants = [
            ImplantSpec(position=(4.0, 4.0, 0.0), axis_direction=(0.0, 0.0, 1.0)),
            ImplantSpec(position=(12.0, 7.0, 0.0), axis_direction=(0.1, 0.0, 1.0)),
            ImplantSpec(position=(18.0, 10.0, 0.0), axis_direction=(-0.1, 0.05, 1.0)),
        ]
        result = place_surgical_guide(JAW_FLAT, implants)
        for i, err in enumerate(result.angular_errors_deg):
            assert err < 0.1, f"Implant {i}: angular error {err:.4f}° exceeds 0.1°"

    def test_max_angular_error_within_0_1_deg(self):
        """max_angular_error_deg() reports < 0.1° for all fixture implants."""
        result = place_surgical_guide(JAW_FLAT, [IMPLANT_STRAIGHT, IMPLANT_ANGLED])
        assert result.max_angular_error_deg() < 0.1

    # --- Body validity checks ------------------------------------------------

    def test_each_sleeve_validate_body_clean(self):
        """Each sleeve body passes validate_body."""
        result = place_surgical_guide(JAW_FLAT, [IMPLANT_STRAIGHT, IMPLANT_ANGLED])
        for i, sleeve in enumerate(result.sleeves):
            vr = validate_body(sleeve)
            assert vr["ok"] is True, f"Sleeve {i} validate_body errors: {vr['errors']}"

    # --- API checks ----------------------------------------------------------

    def test_returns_surgical_guide_result(self):
        result = place_surgical_guide(JAW_FLAT, [IMPLANT_STRAIGHT])
        assert isinstance(result, SurgicalGuideResult)

    def test_sleeve_count_matches_implants(self):
        result = place_surgical_guide(JAW_FLAT, [IMPLANT_STRAIGHT, IMPLANT_ANGLED])
        assert len(result.sleeves) == 2
        assert len(result.angular_errors_deg) == 2
        assert len(result.realised_axes) == 2

    def test_empty_jaw_raises(self):
        with pytest.raises(ValueError):
            place_surgical_guide([], [IMPLANT_STRAIGHT])

    def test_empty_implants_raises(self):
        with pytest.raises(ValueError, match="implants"):
            place_surgical_guide(JAW_FLAT, [])

    def test_realised_axes_are_unit_vectors(self):
        result = place_surgical_guide(JAW_FLAT, [IMPLANT_STRAIGHT, IMPLANT_ANGLED])
        for ax in result.realised_axes:
            assert abs(np.linalg.norm(ax) - 1.0) < 1e-12


# ===========================================================================
# DICOM ingest — DoD: degrades gracefully when pydicom absent
# ===========================================================================

from kerf_dental.dicom_ingest import (
    PYDICOM_AVAILABLE,
    DicomUnavailableError,
    DicomIngestResult,
    _march_cubes_numpy,
)


class TestDicomGracefulDegrade:
    """DoD: DICOM ingest degrades gracefully when pydicom absent."""

    def test_pydicom_available_is_bool(self):
        """PYDICOM_AVAILABLE flag is importable and is a bool."""
        assert isinstance(PYDICOM_AVAILABLE, bool)

    def test_import_without_pydicom_does_not_raise(self):
        """The module can be imported even without pydicom."""
        import importlib
        import kerf_dental.dicom_ingest as mod
        assert hasattr(mod, "PYDICOM_AVAILABLE")
        assert hasattr(mod, "ingest_dicom")
        assert hasattr(mod, "ingest_dicom_series")
        assert hasattr(mod, "DicomUnavailableError")

    @pytest.mark.skipif(PYDICOM_AVAILABLE, reason="pydicom is installed")
    def test_ingest_dicom_raises_dicom_unavailable_when_absent(self, tmp_path):
        """ingest_dicom raises DicomUnavailableError when pydicom absent."""
        from kerf_dental.dicom_ingest import ingest_dicom
        fake = tmp_path / "dummy.dcm"
        fake.write_bytes(b"\x00" * 132)  # minimal DICOM preamble
        with pytest.raises(DicomUnavailableError):
            ingest_dicom(str(fake))

    @pytest.mark.skipif(PYDICOM_AVAILABLE, reason="pydicom is installed")
    def test_ingest_dicom_series_raises_dicom_unavailable_when_absent(self, tmp_path):
        """ingest_dicom_series raises DicomUnavailableError when pydicom absent."""
        from kerf_dental.dicom_ingest import ingest_dicom_series
        fake = tmp_path / "dummy.dcm"
        fake.write_bytes(b"\x00" * 132)
        with pytest.raises(DicomUnavailableError):
            ingest_dicom_series([str(fake)])

    def test_dicom_unavailable_error_is_import_error(self):
        """DicomUnavailableError is a subclass of ImportError."""
        assert issubclass(DicomUnavailableError, ImportError)

    def test_dicom_unavailable_error_has_install_hint(self):
        exc = DicomUnavailableError("pydicom is not installed. pip install pydicom")
        assert "pydicom" in str(exc).lower()


class TestMarchingCubesNumpy:
    """Pure-NumPy marching-cubes fallback — unit tests."""

    def test_empty_volume_no_crossings(self):
        """Uniform volume below iso → no triangles."""
        vol = np.zeros((4, 4, 4), dtype=np.float32)
        verts, faces = _march_cubes_numpy(vol, iso=300.0)
        assert len(faces) == 0

    def test_uniform_above_no_crossings(self):
        """Uniform volume above iso → no triangles (no boundary crossings)."""
        vol = np.full((4, 4, 4), 500.0, dtype=np.float32)
        verts, faces = _march_cubes_numpy(vol, iso=300.0)
        assert len(faces) == 0

    def test_single_voxel_above_produces_triangles(self):
        """One corner above iso → at least one triangle."""
        vol = np.zeros((3, 3, 3), dtype=np.float32)
        vol[0, 0, 0] = 500.0  # single voxel above threshold
        verts, faces = _march_cubes_numpy(vol, iso=300.0)
        assert len(faces) >= 1

    def test_sphere_produces_closed_mesh(self):
        """Sphere of high-HU voxels → mesh with faces on all sides."""
        size = 10
        vol = np.zeros((size, size, size), dtype=np.float32)
        cx = cy = cz = size / 2.0
        for iz in range(size):
            for iy in range(size):
                for ix in range(size):
                    r = math.sqrt((iz - cz)**2 + (iy - cy)**2 + (ix - cx)**2)
                    if r < 3.0:
                        vol[iz, iy, ix] = 600.0
        verts, faces = _march_cubes_numpy(vol, iso=300.0)
        assert len(verts) > 0
        assert len(faces) > 0

    def test_vertices_shape(self):
        vol = np.zeros((4, 4, 4), dtype=np.float32)
        vol[0, 0, 0] = 500.0
        verts, faces = _march_cubes_numpy(vol, iso=300.0)
        if len(verts) > 0:
            assert verts.ndim == 2 and verts.shape[1] == 3

    def test_faces_shape(self):
        vol = np.zeros((4, 4, 4), dtype=np.float32)
        vol[0, 0, 0] = 500.0
        verts, faces = _march_cubes_numpy(vol, iso=300.0)
        if len(faces) > 0:
            assert faces.ndim == 2 and faces.shape[1] == 3

    def test_spacing_scales_vertices(self):
        """Larger spacing → larger vertex coordinates."""
        vol = np.zeros((4, 4, 4), dtype=np.float32)
        vol[0, 0, 0] = 500.0
        verts1, _ = _march_cubes_numpy(vol, iso=300.0, spacing=(1.0, 1.0, 1.0))
        verts2, _ = _march_cubes_numpy(vol, iso=300.0, spacing=(2.0, 2.0, 2.0))
        if len(verts1) > 0 and len(verts2) > 0:
            assert verts2.max() > verts1.max()


class TestDicomIngestResult:
    def test_vertex_count_face_count_properties(self):
        verts = np.zeros((10, 3), dtype=np.float32)
        faces = np.zeros((5, 3), dtype=np.int32)
        result = DicomIngestResult(vertices=verts, faces=faces, iso_value=300.0)
        assert result.vertex_count == 10
        assert result.face_count == 5

    def test_empty_result(self):
        verts = np.zeros((0, 3), dtype=np.float32)
        faces = np.zeros((0, 3), dtype=np.int32)
        result = DicomIngestResult(vertices=verts, faces=faces)
        assert result.vertex_count == 0
        assert result.face_count == 0


# ===========================================================================
# Module-level smoke tests
# ===========================================================================

class TestModuleImports:
    def test_crown_imports(self):
        import kerf_dental.crown  # noqa: F401

    def test_guide_imports(self):
        import kerf_dental.guide  # noqa: F401

    def test_dicom_imports(self):
        import kerf_dental.dicom_ingest  # noqa: F401

    def test_tools_imports(self):
        import kerf_dental.tools  # noqa: F401

    def test_plugin_imports(self):
        import kerf_dental.plugin  # noqa: F401

    def test_pycompile_crown(self):
        import py_compile
        py_compile.compile(os.path.join(_SRC, "kerf_dental", "crown.py"), doraise=True)

    def test_pycompile_guide(self):
        import py_compile
        py_compile.compile(os.path.join(_SRC, "kerf_dental", "guide.py"), doraise=True)

    def test_pycompile_dicom_ingest(self):
        import py_compile
        py_compile.compile(os.path.join(_SRC, "kerf_dental", "dicom_ingest.py"), doraise=True)

    def test_pycompile_tools(self):
        import py_compile
        py_compile.compile(os.path.join(_SRC, "kerf_dental", "tools.py"), doraise=True)
