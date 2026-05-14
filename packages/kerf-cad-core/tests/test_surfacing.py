import pytest
import numpy as np
from kerf_cad_core.geom import (
    NurbsCurve,
    NurbsSurface,
    make_line_nurbs,
    make_circle_nurbs,
    sweep1,
    sweep2,
    network_srf,
    blend_srf,
    validate_curves_for_skinning,
)


def test_make_line_nurbs():
    p1 = np.array([0.0, 0.0, 0.0])
    p2 = np.array([1.0, 0.0, 0.0])
    line = make_line_nurbs(p1, p2)

    assert line.degree == 1
    assert line.num_control_points == 2
    assert np.allclose(line.control_points[0], p1)
    assert np.allclose(line.control_points[1], p2)


def test_make_circle_nurbs():
    center = np.array([0.0, 0.0, 0.0])
    radius = 1.0
    circle = make_circle_nurbs(center, radius)

    assert circle.degree == 2
    assert circle.num_control_points >= 3

    pt_at_0 = circle.evaluate(0.0)
    assert np.isclose(np.linalg.norm(pt_at_0 - center), radius, atol=0.01)


def test_line_evaluate():
    p1 = np.array([0.0, 0.0, 0.0])
    p2 = np.array([1.0, 0.0, 0.0])
    line = make_line_nurbs(p1, p2)

    pt_mid = line.evaluate(0.5)
    assert np.allclose(pt_mid, np.array([0.5, 0.0, 0.0]), atol=0.01)


def test_sweep1_line_along_arc():
    p1 = np.array([0.0, 0.0, 0.0])
    p2 = np.array([1.0, 0.0, 0.0])
    profile = make_line_nurbs(p1, p2)

    arc_center = np.array([0.0, 5.0, 0.0])
    arc = make_circle_nurbs(arc_center, 5.0)

    surface = sweep1(profile, arc, scale=1.0)

    assert isinstance(surface, NurbsSurface)
    assert surface.num_control_points_u == profile.num_control_points
    assert surface.num_control_points_v == arc.num_control_points
    assert surface.degree_u == profile.degree


def test_network_srf_three_curves():
    p1 = np.array([0.0, 0.0, 0.0])
    p2 = np.array([1.0, 0.0, 0.0])
    p3 = np.array([2.0, 0.0, 0.0])

    curve1 = make_line_nurbs(p1 + np.array([0, 0, 0]), p2 + np.array([0, 0, 0]))
    curve2 = make_line_nurbs(p1 + np.array([0, 1, 0]), p2 + np.array([0, 1, 0]))
    curve3 = make_line_nurbs(p1 + np.array([0, 2, 0]), p2 + np.array([0, 2, 0]))

    curves = [curve1, curve2, curve3]

    valid, msg = validate_curves_for_skinning(curves)
    assert valid, msg

    surface = network_srf(curves, degree_u=3)

    assert isinstance(surface, NurbsSurface)
    assert surface.num_control_points_u == len(curves)
    assert surface.control_points.shape[2] == 3


def test_network_srf_invalid():
    curve1 = make_line_nurbs(np.array([0, 0, 0]), np.array([1, 0, 0]))
    curve2 = make_line_nurbs(np.array([0, 1, 0]), np.array([1, 1, 0]))

    valid, _ = validate_curves_for_skinning([curve1])
    assert not valid

    valid, msg = validate_curves_for_skinning([])
    assert not valid


def test_sweep1_output_is_valid_surface():
    profile = make_line_nurbs(np.array([0.0, 0.0, 0.0]), np.array([1.0, 0.0, 0.0]))
    path = make_line_nurbs(np.array([0.0, 0.0, 0.0]), np.array([0.0, 5.0, 0.0]))

    surface = sweep1(profile, path)

    assert isinstance(surface, NurbsSurface)
    assert surface.num_control_points_u == profile.num_control_points
    assert surface.num_control_points_v == path.num_control_points
    assert surface.control_points.ndim == 3
    assert surface.control_points.shape[2] == 3


def test_sweep2_basic():
    profile = make_line_nurbs(np.array([-0.5, 0.0, 0.0]), np.array([0.5, 0.0, 0.0]))

    rail1 = make_line_nurbs(np.array([0.0, 0.0, 0.0]), np.array([0.0, 5.0, 0.0]))
    rail2 = make_line_nurbs(np.array([1.0, 0.0, 0.0]), np.array([1.0, 5.0, 0.0]))

    surface = sweep2(profile, rail1, rail2)

    assert isinstance(surface, NurbsSurface)
    assert surface.num_control_points_u == profile.num_control_points
    assert surface.num_control_points_v == rail1.num_control_points


def test_blend_srf_basic():
    surf1 = NurbsSurface(
        degree_u=2,
        degree_v=2,
        control_points=np.array([
            [[0, 0, 0], [0, 1, 0]],
            [[1, 0, 0], [1, 1, 0]],
            [[2, 0, 0], [2, 1, 0]]
        ]),
        knots_u=np.array([0, 0, 0, 1, 1, 1]),
        knots_v=np.array([0, 0, 0, 1, 1, 1])
    )

    surf2 = NurbsSurface(
        degree_u=2,
        degree_v=2,
        control_points=np.array([
            [[0, 2, 0], [0, 3, 0]],
            [[1, 2, 0], [1, 3, 0]],
            [[2, 2, 0], [2, 3, 0]]
        ]),
        knots_u=np.array([0, 0, 0, 1, 1, 1]),
        knots_v=np.array([0, 0, 0, 1, 1, 1])
    )

    curve1 = make_line_nurbs(np.array([0, 1, 0]), np.array([1, 1, 0]))
    curve2 = make_line_nurbs(np.array([0, 2, 0]), np.array([1, 2, 0]))

    blend_dist = 0.5
    blended = blend_srf(surf1, surf2, curve1, curve2, blend_dist)

    assert isinstance(blended, NurbsSurface)
    assert blended.num_control_points_v > surf1.num_control_points_v


def test_nurbs_surface_evaluate():
    control_pts = np.zeros((3, 3, 3))
    for i in range(3):
        for j in range(3):
            control_pts[i, j] = np.array([i, j, 0.0])

    surface = NurbsSurface(
        degree_u=2,
        degree_v=2,
        control_points=control_pts,
        knots_u=np.array([0, 0, 0, 1, 1, 1]),
        knots_v=np.array([0, 0, 0, 1, 1, 1])
    )

    pt = surface.evaluate(0.5, 0.5)
    assert pt.shape == (3,)


def test_nurbs_curve_derivative():
    line = make_line_nurbs(np.array([0.0, 0.0, 0.0]), np.array([1.0, 1.0, 0.0]))
    deriv = line.derivative(0.5, order=1)

    assert deriv.shape == (3,)
    expected = np.array([1.0, 1.0, 0.0]) / np.sqrt(2)
    assert np.allclose(deriv, expected, atol=0.1)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
