"""
kerf_cad_core.geom — stable public façade for the geometry kernel.

Architecture split
------------------
OCCT-backed (requires OCC runtime, wrapped via kerf_cad_core.geom.brep_build /
boolean / sew):
    surface_to_face, surfaces_to_shell, closed_shell_to_solid
    *_to_body primitives (box, cylinder, sphere, revolve, extrude, loft, sweep1,
        sweep2, extrude_face)
    sew_faces, sew_into_solid
    body_union, body_intersection, body_difference
    shell_body, draft_body, rib_body, wirecut_body, pipe_body
    surface_boolean_robust (OCCT primary path; pure-Python fallback in GK-72)
    STEP / IGES I/O (read_step, write_step, read_iges, write_iges)

Pure-Python (no OCCT dependency, hermetic):
    NurbsCurve / NurbsSurface evaluation, knot insertion, degree elevation
    closest_point_curve, closest_point_surface  (Newton inversion, GK-06/07)
    curve / surface intersection (GK-11/12)
    sweep1 / sweep2 / network_srf / blend_srf / patch_srf / coons
    trim_curve / trim_validation
    curve_toolkit (fairing, curvature comb)
    surface_analysis (Hausdorff, zebra, adaptive refinement)
    surface_fillet (variable-radius G1)
    SubD authoring + SubD↔NURBS conversion (GK-52/53)
    mesh utilities (mesh_autosurface, mesh_boolean_sealed)
    region2d (2-D boolean on planar loops)
    mass_props (body_mass_props)
"""

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
    sweep1_helical,
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
    blend_srf_g3,
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
    extrude_to_body,
    # GK-57: planar region (with holes) → extruded solid
    extrude_face_to_body,
    # GK-16: loft / sweep1 / sweep2 → open Shell Body
    loft_to_body,
    sweep1_to_body,
    sweep2_to_body,
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
# GK-45: shell/hollow a Body (offset faces inward, re-sew).
from kerf_cad_core.geom.solid_features import shell_body
# GK-120: uniform body offset (grow/shrink whole solid).
from kerf_cad_core.geom.solid_features import offset_body
# GK-46: draft/rib/wirecut/pipe as validated Body-producing ops.
from kerf_cad_core.geom.solid_features import (
    draft_body,
    rib_body,
    wirecut_body,
    pipe_body,
)
# GK-44: match-surface analytic G1/G2 verification.
from kerf_cad_core.geom.match_srf import (
    MatchResult,
    match_surface_edge,
    verify_seam_g1_analytic,
    verify_seam_g2_analytic,
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
# GK-65: curvature comb / porcupine numeric export
# GK-98: arc-length parameterization + curve length
# GK-99: mid-curve (average of two NURBS curves)
# GK-100: composite curve (poly-NURBS chain + continuity tags)
from kerf_cad_core.geom.curve_toolkit import (
    fair_curve,
    curvature_variance,
    curvature_comb,
    curve_length,
    arc_length_param,
    mid_curve,
    composite_curve,
    split_composite,
)
# GK-11: curve-curve intersection hardening
from kerf_cad_core.geom.intersection import (
    curve_curve_intersect,
    curve_surface_intersect,
    surface_surface_intersect,
)
# GK-34: surface fit-to-tolerance (lofted/grid least-squares + knot placement)
# GK-99: mid-surface (average of two NURBS surfaces)
from kerf_cad_core.geom.patch_srf import fit_surface, mid_surface
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
# GK-63: deviation-driven adaptive surface refinement
# GK-65: isocurve curvature comb
from kerf_cad_core.geom.surface_analysis import adaptive_refine_surface, isocurve_curvature_comb
# GK-92: draft analysis overlay (angle to pull direction)
from kerf_cad_core.geom.surface_analysis import draft_analysis, curvature_heatmap
# GK-95: reflection-line + highlight-line analysis
from kerf_cad_core.geom.surface_analysis import reflection_lines
# GK-138: global continuity audit
from kerf_cad_core.geom.surface_analysis import continuity_audit
# GK-47: STEP reader
from kerf_cad_core.geom.io.step_read import read_step, StepReadError
# GK-48: STEP writer
from kerf_cad_core.geom.io.step_write import write_step, StepWriteError
# GK-23: body mass properties
from kerf_cad_core.geom.mass_props import body_mass_props
# GK-54: mesh -> NURBS autosurface
from kerf_cad_core.geom.mesh_to_nurbs import mesh_autosurface
# GK-55: mesh boolean sealed-manifold
from kerf_cad_core.geom.mesh_repair import mesh_boolean_sealed, boolean_volume_oracle
# GK-109: mesh decimate (QEM edge collapse)
from kerf_cad_core.geom.mesh_repair import mesh_decimate
# GK-110: mesh repair (hole-fill / weld / manifold / normal-consistency)
from kerf_cad_core.geom.mesh_repair import mesh_repair
# GK-111: mesh smoothing (Laplacian + Taubin λ|μ no-shrink)
from kerf_cad_core.geom.mesh_repair import mesh_smooth
# GK-56: 2D region boolean on planar curve loops
from kerf_cad_core.geom.region2d import (
    region_union,
    region_intersection,
    region_difference,
    region_area,
    make_rect_loop,
    make_circle_loop,
)
# GK-06/07: point inversion (closest-point on curve / surface)
from kerf_cad_core.geom.inversion import (
    closest_point_curve,
    closest_point_surface,
    project_point_to_curve,
    pull_curve_to_surface,
)
# GK-18: pure-Python sew (sew faces into shell / solid)
from kerf_cad_core.geom.sew import (
    sew_faces,
    sew_into_solid,
)
# GK-18: pure-Python boolean (body union / intersection / difference)
from kerf_cad_core.geom.boolean import (
    body_union,
    body_intersection,
    body_difference,
)
# GK-73: inset face (SubD + B-rep)
from kerf_cad_core.geom.inset_face import inset_face, InsetResult
# GK-76: wall-thickness map (printability gate)
from kerf_cad_core.geom.wall_thickness import wall_thickness_map
# GK-29: solid edge/corner blend (concave/convex; degree-3 cylinder/sphere faces)
from kerf_cad_core.geom.blend_solid import (
    BlendResult,
    blend_edge,
    blend_edges,
    blend_corner_vertex,
)
# GK-52: SubD cage → watertight NURBS Body (Catmull-Clark limit surface)
# GK-53: NURBS Body → SubD cage (reverse, quad-dominant)
from kerf_cad_core.geom.subd_to_nurbs import (
    SubdToNurbsError,
    subd_limit_positions,
    subd_cage_to_limit_nurbs_body,
    subd_cage_to_nurbs_body,
    subd_cage_to_nurbs_patches,
    nurbs_body_volume,
    subd_mesh_volume,
    NurbsToSubdError,
    nurbs_body_to_subd_cage,
    nurbs_to_subd_cage,
)
# GK-75: hole feature wrapper (drill / counterbore / countersink / tapped)
from kerf_cad_core.geom.hole_feature import (
    drill_hole,
    counterbore,
    countersink,
    tapped_hole,
)

# GK-74: bridge two open boundary edge loops with a quad strip.
from kerf_cad_core.geom.bridge_loops import (
    BridgeResult,
    bridge_loops,
)
# GK-78: 3MF read/write (sealed manifold + materials + colour + thumbnail)
from kerf_cad_core.geom.io.threemf import (
    read_threemf,
    write_threemf,
    ThreeMFReadError,
    ThreeMFWriteError,
)
# GK-79: glTF 2.0 / GLB read + write (mesh + PBR materials)
from kerf_cad_core.geom.io.gltf import (
    read_gltf,
    write_gltf,
    GltfReadError,
    GltfWriteError,
)
# GK-80: Wavefront OBJ read + write (mesh + groups + mtllib)
from kerf_cad_core.geom.io.obj import (
    read_obj,
    write_obj,
    ObjReadError,
    ObjWriteError,
)
# GK-81: STL read (binary + ASCII) + write
from kerf_cad_core.geom.io.stl import (
    read_stl,
    write_stl,
    StlReadError,
    StlWriteError,
)
# GK-126: PLY read + write (mesh + per-vertex colour; ASCII + binary)
from kerf_cad_core.geom.io.ply import (
    read_ply,
    write_ply,
    PlyReadError,
    PlyWriteError,
)
# GK-88: loop slide (SubD)
from kerf_cad_core.geom.subd_authoring import subd_loop_slide, subd_edge_slide
# GK-106: edge split at parameter (SubD)
from kerf_cad_core.geom.subd_authoring import subd_edge_split
# GK-87: pattern (linear / circular / path)
from kerf_cad_core.geom.pattern import (
    linear_pattern,
    circular_pattern,
    path_pattern,
)

from kerf_cad_core.geom.surface_offset import surface_offset
# GK-96: reverse curve/surface direction
from kerf_cad_core.geom.nurbs import reverse_curve, reverse_surface
# GK-84: split body by plane / surface (no-fill cut)
from kerf_cad_core.geom.split_body import (
    split_body_by_plane,
    split_body_by_surface,
)
# GK-89: knife / cut face by 3D curve (B-rep + SubD)
from kerf_cad_core.geom.knife import knife_face

from kerf_cad_core.geom.replace_face import replace_face
# GK-93: symmetry detection (reflective + rotational)
from kerf_cad_core.geom.symmetry import detect_symmetry
# GK-85: body simplify / heal (remove sub-tol faces/edges, weld verts, close gaps)
from kerf_cad_core.geom.body_heal import simplify_body, heal_body
# GK-82: imprint 3D curve on face → split face creating new edges
from kerf_cad_core.geom.imprint import imprint_curve_on_face
# GK-90: N-rail sweep (3+ rails)
from kerf_cad_core.geom.sweep_n import sweep_n
# GK-91: sheet metal bend / unfold (K-factor + bend tables)
from kerf_cad_core.geom.sheet_metal import (
    K_FACTOR_TABLE,
    bend_allowance,
    bend_sheet,
    unfold_sheet,
)
# GK-129: helical thread profiles (ISO metric + Acme)
# GK-130: spring / coil generator
from kerf_cad_core.geom.threads import (
    iso_metric_thread,
    acme_thread,
    coil_spring,
)

# GK-118: parting line generation
from kerf_cad_core.geom.mold import parting_line, undercut_faces

# GK-125: DXF read+write
from kerf_cad_core.geom.io.dxf import read_dxf, write_dxf, DxfReadError, DxfWriteError

# GK-128: gear tooth profile generator
from kerf_cad_core.geom.gears import involute_gear, cycloid_gear

__all__ = [
    "read_dxf","write_dxf","DxfReadError","DxfWriteError",
    "parting_line","undercut_faces",
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
    # GK-77
    "sweep1_helical",
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
    "blend_srf_g2","blend_srf_g3",
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
    "extrude_to_body",
    # GK-57
    "extrude_face_to_body",
    # GK-16
    "loft_to_body",
    "sweep1_to_body",
    "sweep2_to_body",
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
    "curvature_comb",
    # GK-98
    "curve_length",
    "arc_length_param",
    # GK-99
    "mid_curve",
    # GK-100
    "composite_curve",
    "split_composite",
    # GK-11
    "curve_curve_intersect",
    "curve_surface_intersect",
    "surface_surface_intersect",
    # GK-34
    "fit_surface",
    # GK-99
    "mid_surface",
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
    # GK-63
    "adaptive_refine_surface",
    # GK-65
    "isocurve_curvature_comb",
    # GK-92
    "draft_analysis","curvature_heatmap",
    # GK-95
    "reflection_lines",
    # GK-138
    "continuity_audit",
    "read_step","StepReadError",
    "write_step","StepWriteError",
    # GK-23
    "body_mass_props",
    # GK-54
    "mesh_autosurface",
    # GK-55
    "mesh_boolean_sealed","boolean_volume_oracle",
    # GK-109
    "mesh_decimate",
    # GK-110
    "mesh_repair",
    # GK-111
    "mesh_smooth",
    # GK-56
    "region_union","region_intersection","region_difference",
    "region_area","make_rect_loop","make_circle_loop",
    # GK-44
    "MatchResult","match_surface_edge","verify_seam_g1_analytic","verify_seam_g2_analytic",
    # GK-45
    "shell_body",
    # GK-120
    "offset_body",
    # GK-46
    "draft_body",
    "rib_body",
    "wirecut_body",
    "pipe_body",
    # GK-06/07: closest-point / inversion
    "closest_point_curve",
    "closest_point_surface",
    "project_point_to_curve",
    "pull_curve_to_surface",
    # GK-18: sew
    "sew_faces",
    "sew_into_solid",
    # GK-18: boolean
    "body_union",
    "body_intersection",
    "body_difference",
    # GK-52
    "SubdToNurbsError",
    "subd_limit_positions",
    "subd_cage_to_limit_nurbs_body",
    "subd_cage_to_nurbs_body",
    "subd_cage_to_nurbs_patches",
    "nurbs_body_volume",
    "subd_mesh_volume",
    # GK-53
    "NurbsToSubdError",
    "nurbs_body_to_subd_cage",
    "nurbs_to_subd_cage",
    # GK-73
    "inset_face","InsetResult",
    # GK-76
    "wall_thickness_map",
    # GK-29
    "BlendResult",
    "blend_edge",
    "blend_edges",
    "blend_corner_vertex",
    # GK-74
    "BridgeResult",
    "bridge_loops",
    # GK-78
    "read_threemf",
    "write_threemf",
    "ThreeMFReadError",
    "ThreeMFWriteError",
    # GK-79
    "read_gltf",
    "write_gltf",
    "GltfReadError",
    "GltfWriteError",
    # GK-80
    "read_obj",
    "write_obj",
    "ObjReadError",
    "ObjWriteError",
    # GK-81
    "read_stl",
    "write_stl",
    "StlReadError",
    "StlWriteError",
    # GK-126
    "read_ply",
    "write_ply",
    "PlyReadError",
    "PlyWriteError",
    # GK-96
    "reverse_curve","reverse_surface",
    # GK-83
    "surface_offset",
    # GK-87
    "linear_pattern",
    "circular_pattern",
    "path_pattern",
    # GK-84
    "split_body_by_plane",
    "split_body_by_surface",
    # GK-89
    "knife_face",
    # GK-86
    "replace_face",
    # GK-88
    "subd_loop_slide",
    "subd_edge_slide",
    # GK-106
    "subd_edge_split",
    # GK-93
    "detect_symmetry",
    # GK-85
    "simplify_body",
    "heal_body",
    # GK-82
    "imprint_curve_on_face",
    # GK-90
    "sweep_n",
    # GK-91
    "K_FACTOR_TABLE",
    "bend_allowance",
    "bend_sheet",
    "unfold_sheet",
    # GK-75
    "drill_hole",
    "counterbore",
    "countersink",
    "tapped_hole",
    # GK-122
    "interference",
    # GK-129
    "iso_metric_thread",
    "acme_thread",
    # GK-130
    "coil_spring",
    # GK-112
    "body_sdf",
    "sdf_sample",
    # GK-128
    "involute_gear","cycloid_gear",
    # GK-115
    "gyroid","schwarz_p","octet_truss","kelvin_cell",
    # GK-123
    "clearance",
]

# GK-122: interference / collision detection
from kerf_cad_core.geom.assembly import interference  # noqa: E402

# GK-112: signed distance field from a B-rep Body + trilinear sampler.
from kerf_cad_core.geom.sdf import body_sdf, sdf_sample

# GK-115: lattice unit-cell library (gyroid, Schwarz-P, octet truss, Kelvin cell)
from kerf_cad_core.geom.lattice import gyroid, schwarz_p, octet_truss, kelvin_cell
# GK-123: clearance / minimum-gap analysis
from kerf_cad_core.geom.assembly import clearance  # noqa: E402
