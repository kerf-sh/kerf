"""
Cantilever beam FEM test — verifies the FEniCSx linear-elasticity solve
against the Euler-Bernoulli analytical tip deflection.

Geometry (aligned with x-axis):
  Length  L = 1.0 m
  Width   b = 0.1 m
  Height  h = 0.1 m

Loading:
  Tip face (x = L) loaded with a total downward force F = 1000 N applied as a
  uniform traction t_y = −F / (b * h) over the tip area.

Fixed BC:
  Root face (x = 0) fully clamped.

Analytical tip deflection (Euler-Bernoulli):
  δ = F L³ / (3 E I)    where I = b h³ / 12

Expected tolerance: FEM result within 5 % of the analytical value.
A coarse P1 tetrahedral mesh introduces shear-locking and discretisation
error; 5 % is comfortably achievable at mesh_size = 0.04 for this aspect ratio.

Skips cleanly when dolfinx or gmsh is not installed.
"""

import tempfile
from pathlib import Path

import pytest

pytest.importorskip("dolfinx", reason="dolfinx not installed")
pytest.importorskip("gmsh", reason="gmsh not installed")


# ---------------------------------------------------------------------------
# Beam dimensions
# ---------------------------------------------------------------------------
_L = 1.0    # m  beam length
_b = 0.1    # m  width
_h = 0.1    # m  height


# ---------------------------------------------------------------------------
# Mesh builder
# ---------------------------------------------------------------------------

def _build_beam_msh(msh_path: Path, L: float, b: float, h: float,
                    mesh_size: float) -> None:
    """
    Build a tetrahedral mesh of box beam [0,L] × [0,h] × [0,b] with Gmsh.

    Physical groups assigned:
      volume  tag 1  — the solid
      surface tag 10 — root face (x = 0), used as clamped BC
      surface tag 20 — tip face  (x = L), used as load surface
    """
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
        tip_tags = []
        for _, stag in gmsh.model.getEntities(2):
            xmin, _ym, _zm, xmax, _yM, _zM = gmsh.model.getBoundingBox(2, stag)
            if abs(xmin) < 1e-9 and abs(xmax) < 1e-9:
                root_tags.append(stag)
            elif abs(xmin - L) < 1e-6 and abs(xmax - L) < 1e-6:
                tip_tags.append(stag)

        if root_tags:
            gmsh.model.addPhysicalGroup(2, root_tags, tag=10, name="root")
        if tip_tags:
            gmsh.model.addPhysicalGroup(2, tip_tags, tag=20, name="tip")

        gmsh.model.mesh.generate(3)
        gmsh.write(str(msh_path))
    finally:
        gmsh.finalize()


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------

def test_cantilever_tip_deflection():
    """
    FEM tip deflection must be within 5 % of the Euler-Bernoulli prediction.
    """
    from kerf_fem import fenicsx_utils

    E = 200e9
    nu = 0.3
    yield_strength = 250e6
    F = 1000.0
    L, b, h = _L, _b, _h

    I = b * h**3 / 12.0
    delta_analytical = F * L**3 / (3.0 * E * I)

    material_props = {
        "E": E,
        "nu": nu,
        "yield_strength": yield_strength,
        "rho": 7850.0,
    }
    boundary_conditions = [
        {"type": "fixed", "face_tags": [10]},
    ]
    tip_area = b * h
    loads = [
        {
            "type": "traction",
            "face_tags": [20],
            "direction": [0.0, -1.0, 0.0],
            "value": F / tip_area,
        }
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        msh_path = Path(tmpdir) / "beam.msh"
        _build_beam_msh(msh_path, L, b, h, mesh_size=0.04)

        result = fenicsx_utils._run_linear_static(
            str(msh_path),
            material_props,
            boundary_conditions,
            loads,
        )

    assert not result.get("errors"), f"Solve errors: {result.get('errors')}"

    max_disp = result["max_displacement"]
    assert max_disp > 0.0, "max_displacement should be positive for a loaded beam"

    rel_error = abs(max_disp - delta_analytical) / delta_analytical
    assert rel_error < 0.05, (
        f"Tip deflection {max_disp * 1e3:.4f} mm deviates {rel_error * 100:.1f}% "
        f"from Euler-Bernoulli {delta_analytical * 1e3:.4f} mm (tolerance 5%)"
    )
