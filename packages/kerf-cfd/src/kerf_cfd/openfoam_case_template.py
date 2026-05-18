"""
OpenFOAM case-tree generator.

Writes a minimal but canonical OpenFOAM directory tree under a given root:

    <case>/
        constant/
            transportProperties
            turbulenceProperties
            polyMesh/          (placeholder — blockMeshDict lives in system/)
        system/
            controlDict
            fvSchemes
            fvSolution
            blockMeshDict
        0/
            U
            p
            k              (k-omega SST only)
            omega          (k-omega SST only)
            nut

All dictionaries follow the OpenFOAM foam-format (FoamFile header) that
simpleFoam and pimpleFoam accept without modification.

Supported solver keys
---------------------
"simpleFoam"  — steady-state incompressible RANS
"pimpleFoam"  — transient incompressible RANS / laminar

Supported turbulence model keys
--------------------------------
"laminar"     — RASModel laminar (no extra fields)
"kOmegaSST"   — k-omega SST RANS (writes k and omega initial fields)
"kEpsilon"    — k-epsilon RANS (writes k and epsilon initial fields)

All values are SI.

Reference
---------
OpenFOAM v10 User Guide, ch. 2 — case structure.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Public constants (referenced by tests for structure validation)
# ---------------------------------------------------------------------------

SYSTEM_FILES = ("controlDict", "fvSchemes", "fvSolution", "blockMeshDict")
CONSTANT_FILES = ("transportProperties", "turbulenceProperties")
FIELD_FILES_BASE = ("U", "p", "nut")
FIELD_FILES_K_OMEGA = ("k", "omega")
FIELD_FILES_K_EPSILON = ("k", "epsilon")

SUPPORTED_SOLVERS = ("simpleFoam", "pimpleFoam")
SUPPORTED_TURBULENCE = ("laminar", "kOmegaSST", "kEpsilon")

# ---------------------------------------------------------------------------
# FoamFile header helper
# ---------------------------------------------------------------------------

def _foam_header(foam_class: str, location: str, obj: str) -> str:
    return (
        "FoamFile\n"
        "{\n"
        "    version     2.0;\n"
        "    format      ascii;\n"
        f"    class       {foam_class};\n"
        f"    location    \"{location}\";\n"
        f"    object      {obj};\n"
        "}"
    )


# ---------------------------------------------------------------------------
# system/ files
# ---------------------------------------------------------------------------

def _write_control_dict(path: Path, solver: str, end_time: float,
                        delta_t: float, write_interval: float) -> None:
    content = f"""\
{_foam_header("dictionary", "system", "controlDict")}

application     {solver};

startFrom       startTime;
startTime       0;
stopAt          endTime;
endTime         {end_time:g};

deltaT          {delta_t:g};

writeControl    timeStep;
writeInterval   {int(write_interval)};

purgeWrite      0;
writeFormat     ascii;
writePrecision  6;
writeCompression off;

timeFormat      general;
timePrecision   6;

runTimeModifiable true;

functions
{{
    forces
    {{
        type            forces;
        libs            (forces);
        writeControl    timeStep;
        writeInterval   {int(write_interval)};
        patches         (walls inlet outlet);
        rho             rhoInf;
        rhoInf          1;
        CofR            (0 0 0);
    }}

    fieldAverages
    {{
        type            fieldAverage;
        libs            (fieldFunctionObjects);
        writeControl    endTime;
        fields
        (
            U
            {{
                mean        on;
                prime2Mean  off;
                base        time;
            }}
            p
            {{
                mean        on;
                prime2Mean  off;
                base        time;
            }}
        );
    }}
}}
"""
    path.write_text(content)


def _write_fv_schemes(path: Path, solver: str) -> None:
    if solver == "simpleFoam":
        div_scheme = "Gauss linearUpwind grad(U)"
        time_scheme = "steadyState"
    else:
        div_scheme = "Gauss linearUpwind grad(U)"
        time_scheme = "Euler"

    content = f"""\
{_foam_header("dictionary", "system", "fvSchemes")}

ddtSchemes
{{
    default         {time_scheme};
}}

gradSchemes
{{
    default         Gauss linear;
    grad(U)         Gauss linear;
    grad(p)         Gauss linear;
}}

divSchemes
{{
    default         none;
    div(phi,U)      {div_scheme};
    div(phi,k)      Gauss linearUpwind grad(k);
    div(phi,omega)  Gauss linearUpwind grad(omega);
    div(phi,epsilon) Gauss linearUpwind grad(epsilon);
    div((nuEff*dev(T(grad(U))))) Gauss linear;
    div((nuEff*dev2(T(grad(U))))) Gauss linear;
}}

laplacianSchemes
{{
    default         Gauss linear corrected;
}}

interpolationSchemes
{{
    default         linear;
}}

snGradSchemes
{{
    default         corrected;
}}

wallDist
{{
    method          meshWave;
}}
"""
    path.write_text(content)


def _write_fv_solution(path: Path, solver: str) -> None:
    if solver == "simpleFoam":
        algo_block = """\
SIMPLE
{
    nNonOrthogonalCorrectors 0;
    consistent      yes;
    residualControl
    {
        p               1e-4;
        U               1e-4;
        "(k|omega|epsilon)" 1e-4;
    }
}

relaxationFactors
{
    fields
    {
        p               0.3;
    }
    equations
    {
        U               0.7;
        k               0.7;
        omega           0.7;
        epsilon         0.7;
    }
}"""
    else:
        algo_block = """\
PIMPLE
{
    nOuterCorrectors 1;
    nCorrectors      2;
    nNonOrthogonalCorrectors 0;
}

relaxationFactors
{
    equations
    {
        U               0.9;
        k               0.9;
        omega           0.9;
        epsilon         0.9;
    }
}"""

    content = f"""\
{_foam_header("dictionary", "system", "fvSolution")}

solvers
{{
    p
    {{
        solver          GAMG;
        smoother        GaussSeidel;
        tolerance       1e-7;
        relTol          0.01;
    }}

    pFinal
    {{
        $p;
        relTol          0;
    }}

    "(U|k|omega|epsilon|nut)"
    {{
        solver          smoothSolver;
        smoother        symGaussSeidel;
        tolerance       1e-8;
        relTol          0.1;
    }}

    "(U|k|omega|epsilon|nut)Final"
    {{
        $U;
        relTol          0;
    }}
}}

{algo_block}
"""
    path.write_text(content)


def _write_block_mesh_dict(path: Path, geometry: dict[str, Any]) -> None:
    """Write a blockMeshDict for a simple rectangular pipe/channel."""
    x0 = geometry.get("x0", 0.0)
    y0 = geometry.get("y0", 0.0)
    z0 = geometry.get("z0", 0.0)
    x1 = geometry.get("x1", 1.0)
    y1 = geometry.get("y1", 0.1)
    z1 = geometry.get("z1", 0.1)
    nx = geometry.get("nx", 20)
    ny = geometry.get("ny", 10)
    nz = geometry.get("nz", 1)

    content = f"""\
{_foam_header("dictionary", "system", "blockMeshDict")}

scale 1;

vertices
(
    ({x0:g} {y0:g} {z0:g})  // 0
    ({x1:g} {y0:g} {z0:g})  // 1
    ({x1:g} {y1:g} {z0:g})  // 2
    ({x0:g} {y1:g} {z0:g})  // 3
    ({x0:g} {y0:g} {z1:g})  // 4
    ({x1:g} {y0:g} {z1:g})  // 5
    ({x1:g} {y1:g} {z1:g})  // 6
    ({x0:g} {y1:g} {z1:g})  // 7
);

blocks
(
    hex (0 1 2 3 4 5 6 7) ({nx} {ny} {nz}) simpleGrading (1 1 1)
);

edges
(
);

boundary
(
    inlet
    {{
        type patch;
        faces
        (
            (0 4 7 3)
        );
    }}
    outlet
    {{
        type patch;
        faces
        (
            (1 2 6 5)
        );
    }}
    walls
    {{
        type wall;
        faces
        (
            (0 1 5 4)
            (3 7 6 2)
        );
    }}
    frontAndBack
    {{
        type empty;
        faces
        (
            (0 3 2 1)
            (4 5 6 7)
        );
    }}
);

mergePatchPairs
(
);
"""
    path.write_text(content)


# ---------------------------------------------------------------------------
# constant/ files
# ---------------------------------------------------------------------------

def _write_transport_properties(path: Path, nu: float) -> None:
    content = f"""\
{_foam_header("dictionary", "constant", "transportProperties")}

transportModel  Newtonian;

nu              {nu:g};
"""
    path.write_text(content)


def _write_turbulence_properties(path: Path, turbulence_model: str) -> None:
    if turbulence_model == "laminar":
        ras_model = "laminar"
        turb_on = "off"
    elif turbulence_model == "kOmegaSST":
        ras_model = "kOmegaSST"
        turb_on = "on"
    elif turbulence_model == "kEpsilon":
        ras_model = "kEpsilon"
        turb_on = "on"
    else:
        raise ValueError(f"unsupported turbulence model: {turbulence_model!r}")

    content = f"""\
{_foam_header("dictionary", "constant", "turbulenceProperties")}

simulationType  RAS;

RAS
{{
    RASModel    {ras_model};
    turbulence  {turb_on};
    printCoeffs on;
}}
"""
    path.write_text(content)


# ---------------------------------------------------------------------------
# 0/ initial condition files
# ---------------------------------------------------------------------------

def _write_U(path: Path, u_inlet: float) -> None:
    content = f"""\
{_foam_header("volVectorField", "0", "U")}

dimensions      [0 1 -1 0 0 0 0];

internalField   uniform (0 0 0);

boundaryField
{{
    inlet
    {{
        type            fixedValue;
        value           uniform ({u_inlet:g} 0 0);
    }}
    outlet
    {{
        type            zeroGradient;
    }}
    walls
    {{
        type            noSlip;
    }}
    frontAndBack
    {{
        type            empty;
    }}
}}
"""
    path.write_text(content)


def _write_p(path: Path) -> None:
    content = f"""\
{_foam_header("volScalarField", "0", "p")}

dimensions      [0 2 -2 0 0 0 0];

internalField   uniform 0;

boundaryField
{{
    inlet
    {{
        type            zeroGradient;
    }}
    outlet
    {{
        type            fixedValue;
        value           uniform 0;
    }}
    walls
    {{
        type            zeroGradient;
    }}
    frontAndBack
    {{
        type            empty;
    }}
}}
"""
    path.write_text(content)


def _write_nut(path: Path) -> None:
    content = f"""\
{_foam_header("volScalarField", "0", "nut")}

dimensions      [0 2 -1 0 0 0 0];

internalField   uniform 0;

boundaryField
{{
    inlet
    {{
        type            calculated;
        value           uniform 0;
    }}
    outlet
    {{
        type            calculated;
        value           uniform 0;
    }}
    walls
    {{
        type            nutkWallFunction;
        value           uniform 0;
    }}
    frontAndBack
    {{
        type            empty;
    }}
}}
"""
    path.write_text(content)


def _write_k(path: Path, k_inlet: float) -> None:
    content = f"""\
{_foam_header("volScalarField", "0", "k")}

dimensions      [0 2 -2 0 0 0 0];

internalField   uniform {k_inlet:g};

boundaryField
{{
    inlet
    {{
        type            fixedValue;
        value           uniform {k_inlet:g};
    }}
    outlet
    {{
        type            zeroGradient;
    }}
    walls
    {{
        type            kqRWallFunction;
        value           uniform {k_inlet:g};
    }}
    frontAndBack
    {{
        type            empty;
    }}
}}
"""
    path.write_text(content)


def _write_omega(path: Path, omega_inlet: float) -> None:
    content = f"""\
{_foam_header("volScalarField", "0", "omega")}

dimensions      [0 0 -1 0 0 0 0];

internalField   uniform {omega_inlet:g};

boundaryField
{{
    inlet
    {{
        type            fixedValue;
        value           uniform {omega_inlet:g};
    }}
    outlet
    {{
        type            zeroGradient;
    }}
    walls
    {{
        type            omegaWallFunction;
        value           uniform {omega_inlet:g};
    }}
    frontAndBack
    {{
        type            empty;
    }}
}}
"""
    path.write_text(content)


def _write_epsilon(path: Path, epsilon_inlet: float) -> None:
    content = f"""\
{_foam_header("volScalarField", "0", "epsilon")}

dimensions      [0 2 -3 0 0 0 0];

internalField   uniform {epsilon_inlet:g};

boundaryField
{{
    inlet
    {{
        type            fixedValue;
        value           uniform {epsilon_inlet:g};
    }}
    outlet
    {{
        type            zeroGradient;
    }}
    walls
    {{
        type            epsilonWallFunction;
        value           uniform {epsilon_inlet:g};
    }}
    frontAndBack
    {{
        type            empty;
    }}
}}
"""
    path.write_text(content)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_case(
    case_dir: str | Path,
    *,
    solver: str = "simpleFoam",
    turbulence_model: str = "laminar",
    nu: float = 1e-5,
    u_inlet: float = 1.0,
    end_time: float = 500.0,
    delta_t: float = 1.0,
    write_interval: float = 100.0,
    geometry: dict[str, Any] | None = None,
    # turbulence initial conditions (reasonable defaults for low-turbulence inlets)
    k_inlet: float = 0.001,
    omega_inlet: float = 1.0,
    epsilon_inlet: float = 0.001,
) -> Path:
    """
    Write a complete OpenFOAM case directory tree under *case_dir*.

    Returns the resolved Path to the case root (same as *case_dir*).

    Parameters
    ----------
    case_dir : str | Path
        Destination directory (created if it does not exist).
    solver : {"simpleFoam", "pimpleFoam"}
        OpenFOAM application to target.
    turbulence_model : {"laminar", "kOmegaSST", "kEpsilon"}
        RANS model; "laminar" skips turbulence fields.
    nu : float
        Kinematic viscosity (m²/s).
    u_inlet : float
        Mean inlet velocity magnitude (m/s, x-direction).
    end_time : float
        Simulation end time (iterations for simpleFoam, seconds for pimpleFoam).
    delta_t : float
        Time step (seconds, or 1 for steady-state iterations).
    write_interval : float
        Result write interval (time steps).
    geometry : dict | None
        Rectangular block geometry keys: x0, y0, z0, x1, y1, z1, nx, ny, nz.
        Defaults to unit cube with nx=20, ny=10, nz=1.
    k_inlet : float
        Turbulent kinetic energy at inlet (m²/s²).
    omega_inlet : float
        Specific dissipation rate at inlet (1/s).
    epsilon_inlet : float
        Turbulent dissipation rate at inlet (m²/s³).

    Raises
    ------
    ValueError
        If *solver* or *turbulence_model* are not in the supported sets.
    """
    if solver not in SUPPORTED_SOLVERS:
        raise ValueError(
            f"solver {solver!r} not supported; choose from {SUPPORTED_SOLVERS}"
        )
    if turbulence_model not in SUPPORTED_TURBULENCE:
        raise ValueError(
            f"turbulence_model {turbulence_model!r} not supported; "
            f"choose from {SUPPORTED_TURBULENCE}"
        )

    root = Path(case_dir).resolve()
    system_dir = root / "system"
    constant_dir = root / "constant"
    zero_dir = root / "0"
    poly_mesh_dir = constant_dir / "polyMesh"

    for d in (system_dir, constant_dir, zero_dir, poly_mesh_dir):
        d.mkdir(parents=True, exist_ok=True)

    geom = geometry or {}

    # system/
    _write_control_dict(system_dir / "controlDict", solver, end_time, delta_t, write_interval)
    _write_fv_schemes(system_dir / "fvSchemes", solver)
    _write_fv_solution(system_dir / "fvSolution", solver)
    _write_block_mesh_dict(system_dir / "blockMeshDict", geom)

    # constant/
    _write_transport_properties(constant_dir / "transportProperties", nu)
    _write_turbulence_properties(constant_dir / "turbulenceProperties", turbulence_model)

    # 0/
    _write_U(zero_dir / "U", u_inlet)
    _write_p(zero_dir / "p")
    _write_nut(zero_dir / "nut")

    if turbulence_model == "kOmegaSST":
        _write_k(zero_dir / "k", k_inlet)
        _write_omega(zero_dir / "omega", omega_inlet)
    elif turbulence_model == "kEpsilon":
        _write_k(zero_dir / "k", k_inlet)
        _write_epsilon(zero_dir / "epsilon", epsilon_inlet)

    return root
