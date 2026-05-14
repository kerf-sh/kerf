"""
Modal analysis test — verifies the SLEPc eigensolver returns the first natural
frequency of a spring-mass beam within 5 % of the analytical value.

Setup: a short prismatic beam with one end clamped.

Analytical first bending frequency (Euler-Bernoulli):
  f₁ = (β₁ L)² / (2π L²) · √(E I / (ρ A))

  (β₁ L)² ≈ 3.5160  for a clamped-free beam (first mode)

This test requires dolfinx + gmsh + slepc4py.  Missing any of these causes a
clean skip (pytest.importorskip).
"""

import math
import tempfile
from pathlib import Path

import pytest

pytest.importorskip("dolfinx", reason="dolfinx not installed")
pytest.importorskip("gmsh", reason="gmsh not installed")
slepc4py = pytest.importorskip("slepc4py", reason="slepc4py not installed")


# ---------------------------------------------------------------------------
# Beam parameters
# ---------------------------------------------------------------------------
_L = 0.5    # m  beam length
_b = 0.05   # m  width
_h = 0.05   # m  height
_E = 200e9  # Pa
_nu = 0.3
_rho = 7850.0  # kg/m³


def _analytical_first_freq(L, b, h, E, rho):
    """Euler-Bernoulli clamped-free first bending frequency."""
    I = b * h**3 / 12.0
    A = b * h
    beta1_L = 1.8751  # (β₁ L) for clamped-free mode 1
    # f = (β₁ L)² / (2π L²) * √(E I / (ρ A))
    return (beta1_L**2) / (2 * math.pi * L**2) * math.sqrt(E * I / (rho * A))


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


def test_modal_first_frequency():
    """
    First natural frequency from SLEPc GHEP must be within 5 % of the
    Euler-Bernoulli analytical value for a clamped-free beam.
    """
    from kerf_fem import fenicsx_utils

    material_props = {
        "E": _E,
        "nu": _nu,
        "rho": _rho,
        "yield_strength": 250e6,
    }
    boundary_conditions = [{"type": "fixed", "face_tags": [10]}]

    with tempfile.TemporaryDirectory() as tmpdir:
        msh_path = Path(tmpdir) / "beam.msh"
        _build_beam_msh(msh_path, _L, _b, _h, mesh_size=0.025)

        result = fenicsx_utils._run_modal(
            str(msh_path),
            material_props,
            boundary_conditions,
        )

    if result.get("warnings") and "SLEPc not installed" in result["warnings"][0]:
        pytest.skip("SLEPc not available at runtime")

    assert not result.get("errors"), f"Modal errors: {result.get('errors')}"
    freqs = result["frequencies"]
    assert len(freqs) >= 1, "Expected at least one converged frequency"

    f_fem = freqs[0]
    f_analytical = _analytical_first_freq(_L, _b, _h, _E, _rho)

    rel_err = abs(f_fem - f_analytical) / f_analytical
    assert rel_err < 0.05, (
        f"First mode {f_fem:.2f} Hz deviates {rel_err*100:.1f}% "
        f"from analytical {f_analytical:.2f} Hz (tolerance 5%)"
    )


def test_modal_returns_mode_shapes():
    """mode_shapes must be present and match number of frequencies."""
    from kerf_fem import fenicsx_utils

    material_props = {"E": _E, "nu": _nu, "rho": _rho, "yield_strength": 250e6}
    boundary_conditions = [{"type": "fixed", "face_tags": [10]}]

    with tempfile.TemporaryDirectory() as tmpdir:
        msh_path = Path(tmpdir) / "beam.msh"
        _build_beam_msh(msh_path, _L, _b, _h, mesh_size=0.04)

        result = fenicsx_utils._run_modal(
            str(msh_path),
            material_props,
            boundary_conditions,
        )

    if result.get("warnings") and "SLEPc not installed" in result["warnings"][0]:
        pytest.skip("SLEPc not available at runtime")

    freqs = result["frequencies"]
    shapes = result.get("mode_shapes", [])
    assert len(shapes) == len(freqs), (
        f"mode_shapes length {len(shapes)} != frequencies length {len(freqs)}"
    )
    if shapes:
        assert all(k in shapes[0][0] for k in ("ux", "uy", "uz")), (
            "mode shape entries must have ux/uy/uz keys"
        )
