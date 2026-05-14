"""
CalculiX modal analysis test.

Verifies that the first bending frequency of a clamped-free cantilever beam
is within 5 % of the Euler-Bernoulli analytical value.

Euler-Bernoulli clamped-free first bending mode:
    f₁ = (β₁ L)² / (2π L²) · √(E I / (ρ A))
    β₁ L ≈ 1.8751

Skips cleanly when ccx (CalculiX) or gmsh is absent.
"""

import math
import shutil
import tempfile
from pathlib import Path

import pytest

# Applied per-test via marker rather than pytestmark so the pending test runs
# even when ccx is absent.
_needs_ccx = pytest.mark.skipif(
    shutil.which("ccx") is None,
    reason="ccx (CalculiX) not installed or not in PATH",
)

# ---------------------------------------------------------------------------
# Beam parameters
# ---------------------------------------------------------------------------
_L = 0.5    # m  beam length
_b = 0.05   # m  width
_h = 0.05   # m  height
_E = 200e9  # Pa  Young's modulus
_nu = 0.3
_rho = 7850.0  # kg/m³


def _analytical_first_freq(L, b, h, E, rho):
    """Euler-Bernoulli clamped-free first bending frequency (Hz)."""
    I = b * h ** 3 / 12.0
    A = b * h
    beta1_L = 1.8751  # first eigenvalue for clamped-free mode
    return (beta1_L ** 2) / (2 * math.pi * L ** 2) * math.sqrt(E * I / (rho * A))


def _build_beam_msh(msh_path: Path, L, b, h, mesh_size=0.025):
    import gmsh

    gmsh.initialize()
    gmsh.option.setNumber("General.Terminal", 0)
    gmsh.option.setNumber("Mesh.CharacteristicSizeMax", mesh_size)
    gmsh.option.setNumber("Mesh.Algorithm3D", 10)
    try:
        vol_tag = gmsh.model.occ.addBox(0.0, 0.0, 0.0, L, h, b)
        gmsh.model.occ.synchronize()
        gmsh.model.addPhysicalGroup(3, [vol_tag], tag=1, name="vol")

        root_tags = []
        for _, stag in gmsh.model.getEntities(2):
            xmin, _, _, xmax, _, _ = gmsh.model.getBoundingBox(2, stag)
            if abs(xmin) < 1e-9 and abs(xmax) < 1e-9:
                root_tags.append(stag)
        if root_tags:
            gmsh.model.addPhysicalGroup(2, root_tags, tag=10, name="root")

        gmsh.model.mesh.generate(3)
        gmsh.write(str(msh_path))
    finally:
        gmsh.finalize()


def _load_calculix_utils():
    from kerf_fem import calculix_utils
    return calculix_utils


@_needs_ccx
def test_calculix_modal_first_frequency():
    """First natural frequency must be within 5 % of the Euler-Bernoulli value."""
    pytest.importorskip("gmsh", reason="gmsh not installed")
    ccu = _load_calculix_utils()
    material_props = {"E": _E, "nu": _nu, "rho": _rho, "yield_strength": 250e6}
    # face_tag 1 maps to x=xmin face (root/clamped end) in _build_face_node_sets
    boundary_conditions = [{"type": "fixed", "face_tags": [1]}]

    with tempfile.TemporaryDirectory() as tmpdir:
        msh_path = Path(tmpdir) / "beam.msh"
        _build_beam_msh(msh_path, _L, _b, _h, mesh_size=0.025)

        result = ccu._run_calculix_modal(
            str(msh_path),
            material_props,
            boundary_conditions,
        )

    assert not result.get("errors"), f"Modal errors: {result.get('errors')}"
    freqs = result.get("frequencies", [])
    assert len(freqs) >= 1, "Expected at least one frequency from CalculiX modal"

    f_fem = freqs[0]
    f_analytical = _analytical_first_freq(_L, _b, _h, _E, _rho)

    rel_err = abs(f_fem - f_analytical) / f_analytical
    assert rel_err < 0.05, (
        f"First mode {f_fem:.2f} Hz deviates {rel_err * 100:.1f}% "
        f"from analytical {f_analytical:.2f} Hz (tolerance 5%)"
    )


@_needs_ccx
def test_calculix_modal_returns_mode_shapes():
    """mode_shapes list must be present and have the same length as frequencies."""
    pytest.importorskip("gmsh", reason="gmsh not installed")
    ccu = _load_calculix_utils()
    material_props = {"E": _E, "nu": _nu, "rho": _rho, "yield_strength": 250e6}
    boundary_conditions = [{"type": "fixed", "face_tags": [1]}]

    with tempfile.TemporaryDirectory() as tmpdir:
        msh_path = Path(tmpdir) / "beam.msh"
        _build_beam_msh(msh_path, _L, _b, _h, mesh_size=0.04)

        result = ccu._run_calculix_modal(
            str(msh_path),
            material_props,
            boundary_conditions,
        )

    freqs = result.get("frequencies", [])
    shapes = result.get("mode_shapes", [])
    assert len(shapes) == len(freqs), (
        f"mode_shapes length {len(shapes)} != frequencies length {len(freqs)}"
    )
    if shapes:
        node = shapes[0][0]
        assert all(k in node for k in ("ux", "uy", "uz")), (
            "mode shape node entries must have ux/uy/uz keys"
        )


def test_calculix_modal_pending_without_ccx(monkeypatch):
    """When ccx is not available, run_static_analysis returns a pending sentinel."""
    import shutil as _shutil
    ccu = _load_calculix_utils()
    monkeypatch.setattr(_shutil, "which", lambda _: None)
    # Reset the cached flag so the monkeypatch takes effect.
    ccu._CALCULIX_AVAILABLE = None
    result = ccu.run_static_analysis(
        mesh_path="dummy.msh",
        material_props={},
        boundary_conditions=[],
        loads=[],
        analysis_type="modal",
    )
    assert result.get("status") == "pending"
    assert any("ccx" in w.lower() or "calculix" in w.lower()
               for w in result.get("warnings", []))
