"""NURBS surface helpers for kerf-cad-core."""

from kerf_cad_core.geom.nurbs import (
    NurbsCurve,
    NurbsSurface,
    de_boor,
    curve_derivative,
    surface_evaluate,
    knot_insertion,
    degree_elevation,
    curve_curve_intersection,
    make_circle_nurbs,
    make_line_nurbs,
    nurbs_to_occt_curve,
    occt_curve_to_nurbs,
    nurbs_to_occt_surface,
    occt_surface_to_nurbs,
)

from kerf_cad_core.geom.sweep1 import (
    sweep1,
    sweep1_rmf,
    sweep1_with_twist,
    sweep1_variable_scale,
    profile_along_path,
    compute_rmf_frames,
)

from kerf_cad_core.geom.sweep2 import (
    sweep2,
    sweep2_rmf,
    sweep2_with_scaling,
    sweep2_with_twist,
    check_rail_compatibility,
    normalize_rails,
)

from kerf_cad_core.geom.network_srf import (
    network_srf,
    network_srf_with_compatibility,
    network_srf_global,
    network_srf_from_cross_sections,
    approximate_network_srf,
    validate_curves_for_skinning,
    gordon_network_srf,
)

from kerf_cad_core.geom.blend_srf import (
    blend_srf,
    blend_srf_g1,
    blend_srf_g2,
    blend_srf_with_curves,
    blend_srf_fillet,
    validate_surface_blend,
    compute_blend_surface_isocurves,
)

from kerf_cad_core.geom.surface_boolean_robust import (
    surface_health_check,
    surface_boolean_robust,
)

from kerf_cad_core.geom.brep_build import (
    BuildError,
    surface_to_face,
    surfaces_to_shell,
    closed_shell_to_solid,
    box_to_body,
    cylinder_to_body,
    sphere_to_body,
    revolve_to_body,
)

from kerf_cad_core.geom.subd_authoring import (
    SubDCage,
    SubDSurface,
    create_subd_primitive,
    subd_extrude,
    subd_bevel,
    subd_loop_cut,
    subd_set_crease,
    to_subd_surface,
)
# T-104e: pure-Python trim side-selection + validation contract.
from kerf_cad_core.geom.trim_validation import (
    AmbiguousPoint,
    select_side,
    validate_body_post_trim,
)

# GK-39: untrim / shrink trimmed surface.
from kerf_cad_core.geom.trim_curve import (
    trim_face_by_ssi,
    trim_face_analytic,
    SsiTrimResult,
    AnalyticTrimLoop,
    TrimmedSurface,
    untrim,
    shrink,
)
# GK-35: energy-minimising, knot-preserving curve fairing
from kerf_cad_core.geom.curve_toolkit import (
    fair_curve,
    curvature_variance,
)
# GK-11: curve-curve intersection hardening
from kerf_cad_core.geom.intersection import (
    curve_curve_intersect,
    curve_surface_intersect,
    surface_surface_intersect,
)
# GK-34: surface fit-to-tolerance (lofted/grid least-squares + knot placement)
from kerf_cad_core.geom.patch_srf import fit_surface
# GK-12: curve self-intersection
from kerf_cad_core.geom.intersection import curve_self_intersect
# GK-49: IGES 144 trimmed-surface reader/writer
from kerf_cad_core.geom.io.iges import (
    write_iges,
    read_iges,
    IgesReadError,
    IgesWriteError,
)
# GK-37: certified Hausdorff surface deviation
from kerf_cad_core.geom.surface_fillet import variable_radius_fillet_g1
from kerf_cad_core.geom.surface_analysis import hausdorff_deviation, zebra_stripe, zebra_stripe_continuity_analyser
# GK-47: STEP reader
from kerf_cad_core.geom.io.step_read import read_step, StepReadError
# GK-23: body mass properties
from kerf_cad_core.geom.mass_props import body_mass_props
# GK-55: mesh boolean sealed-manifold
from kerf_cad_core.geom.mesh_repair import mesh_boolean_sealed, boolean_volume_oracle
# GK-56: 2D region boolean on planar curve loops
from kerf_cad_core.geom.region2d import (
    region_union,
    region_intersection,
    region_difference,
    region_area,
    make_rect_loop,
    make_circle_loop,
)

__all__ = [
    "NurbsCurve",
    "NurbsSurface",
    "de_boor",
    "curve_derivative",
    "surface_evaluate",
    "knot_insertion",
    "degree_elevation",
    "curve_curve_intersection",
    "make_circle_nurbs",
    "make_line_nurbs",
    "nurbs_to_occt_curve",
    "occt_curve_to_nurbs",
    "nurbs_to_occt_surface",
    "occt_surface_to_nurbs",
    "sweep1",
    "sweep1_rmf",
    "sweep1_with_twist",
    "sweep1_variable_scale",
    "profile_along_path",
    "compute_rmf_frames",
    "sweep2",
    "sweep2_rmf",
    "sweep2_with_scaling",
    "sweep2_with_twist",
    "check_rail_compatibility",
    "normalize_rails",
    "network_srf",
    "network_srf_with_compatibility",
    "network_srf_global",
    "network_srf_from_cross_sections",
    "approximate_network_srf",
    "validate_curves_for_skinning",
    "gordon_network_srf",
    "blend_srf",
    "blend_srf_g1",
    "blend_srf_g2",
    "blend_srf_with_curves",
    "blend_srf_fillet",
    "validate_surface_blend",
    "compute_blend_surface_isocurves",
    "surface_health_check",
    "surface_boolean_robust",
    "BuildError",
    "surface_to_face",
    "surfaces_to_shell",
    "closed_shell_to_solid",
    "box_to_body",
    "cylinder_to_body",
    "sphere_to_body",
    "revolve_to_body",
    "SubDCage",
    "SubDSurface",
    "create_subd_primitive",
    "subd_extrude",
    "subd_bevel",
    "subd_loop_cut",
    "subd_set_crease",
    "to_subd_surface",
    "AmbiguousPoint",
    "select_side",
    "validate_body_post_trim",
    "TrimmedSurface",
    "trim_face_by_ssi","trim_face_analytic","SsiTrimResult","AnalyticTrimLoop",
    "untrim",
    "shrink",
    "fair_curve",
    "curvature_variance",
    # GK-11
    "curve_curve_intersect",
    "curve_surface_intersect",
    "surface_surface_intersect",
    # GK-34
    "fit_surface",
    # GK-12
    "curve_self_intersect",
    # GK-49
    "write_iges",
    "read_iges",
    "IgesReadError",
    "IgesWriteError",
    # GK-37
    "variable_radius_fillet_g1",
    "hausdorff_deviation","zebra_stripe","zebra_stripe_continuity_analyser",
    "read_step","StepReadError",
    # GK-23
    "body_mass_props",
    # GK-55
    "mesh_boolean_sealed","boolean_volume_oracle",
    # GK-56
    "region_union","region_intersection","region_difference",
    "region_area","make_rect_loop","make_circle_loop",
]
