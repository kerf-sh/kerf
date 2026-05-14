import unittest
import math
from kerf_mates.solver import (
    Entity,
    MateConstraint,
    GeometricConstraintSolver,
    compute_tolerance_stackup,
    solve_assembly,
    vec3_distance,
    vec3_angle,
)


class TestVec3Operations(unittest.TestCase):
    def test_vec3_distance(self):
        a = (0.0, 0.0, 0.0)
        b = (3.0, 4.0, 0.0)
        self.assertAlmostEqual(vec3_distance(a, b), 5.0)

    def test_vec3_distance_same_point(self):
        a = (1.0, 2.0, 3.0)
        self.assertAlmostEqual(vec3_distance(a, a), 0.0)

    def test_vec3_angle(self):
        a = (1.0, 0.0, 0.0)
        b = (0.0, 1.0, 0.0)
        self.assertAlmostEqual(vec3_angle(a, b), math.pi / 2)


class TestGeometricConstraintSolver(unittest.TestCase):
    def test_coincident_constraint(self):
        entities = [
            Entity(id="p1", entity_type="vertex", component_id="c1", feature_id="v1", position=(0.0, 0.0, 0.0)),
            Entity(id="p2", entity_type="vertex", component_id="c2", feature_id="v1", position=(10.0, 0.0, 0.0)),
        ]
        constraints = [
            MateConstraint(id="m1", mate_type="coincident", entity_a_id="p1", entity_b_id="p2"),
        ]

        solver = GeometricConstraintSolver(entities, constraints)
        result = solver.solve()

        self.assertTrue(result.solved)
        self.assertAlmostEqual(vec3_distance(result.entities["p1"].position, result.entities["p2"].position), 0.0, places=3)

    def test_distance_constraint(self):
        entities = [
            Entity(id="p1", entity_type="vertex", component_id="c1", feature_id="v1", position=(0.0, 0.0, 0.0)),
            Entity(id="p2", entity_type="vertex", component_id="c2", feature_id="v1", position=(15.0, 0.0, 0.0)),
        ]
        constraints = [
            MateConstraint(id="m1", mate_type="distance", entity_a_id="p1", entity_b_id="p2", value=10.0, unit="mm"),
        ]

        solver = GeometricConstraintSolver(entities, constraints)
        result = solver.solve()

        self.assertTrue(result.solved)
        self.assertAlmostEqual(vec3_distance(result.entities["p1"].position, result.entities["p2"].position), 10.0, places=2)


class TestToleranceStackup(unittest.TestCase):
    def test_distance_tolerance_worst_case(self):
        constraints = [
            MateConstraint(
                id="m1",
                mate_type="distance",
                entity_a_id="p1",
                entity_b_id="p2",
                value=10.0,
                unit="mm",
                tolerance_plus=0.1,
                tolerance_minus=0.05,
            ),
        ]

        result = compute_tolerance_stackup(constraints)

        self.assertIn("m1", result)
        self.assertEqual(result["m1"]["nominal"], 10.0)
        self.assertEqual(result["m1"]["worst_case"]["max"], 10.1)
        self.assertEqual(result["m1"]["worst_case"]["min"], 9.95)

    def test_distance_tolerance_rss(self):
        constraints = [
            MateConstraint(
                id="m1",
                mate_type="distance",
                entity_a_id="p1",
                entity_b_id="p2",
                value=10.0,
                unit="mm",
                tolerance_plus=0.1,
                tolerance_minus=0.1,
            ),
        ]

        result = compute_tolerance_stackup(constraints)

        expected_rss_band = math.sqrt(0.1 ** 2 + 0.1 ** 2)
        self.assertAlmostEqual(result["m1"]["rss"]["band"], expected_rss_band)


class TestSolveAssembly(unittest.TestCase):
    def test_two_parts_coincident_mate(self):
        components = [
            {"id": "comp1", "transform": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]},
            {"id": "comp2", "transform": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 10, 0, 0, 1]},
        ]
        mates = [
            {
                "id": "mate1",
                "type": "coincident",
                "a": {"component_id": "comp1", "feature": "face", "feature_id": "plane_xy"},
                "b": {"component_id": "comp2", "feature": "face", "feature_id": "plane_xy"},
            },
        ]

        result = solve_assembly(components, mates, fixed_component_id="comp1")

        self.assertIn("solved", result)
        self.assertIn("component_transforms", result)
        self.assertIn("tolerance_stackup", result)

    def test_distance_mate_with_tolerance(self):
        components = [
            {"id": "comp1", "transform": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]},
            {"id": "comp2", "transform": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 20, 0, 0, 1]},
        ]
        mates = [
            {
                "id": "mate1",
                "type": "distance",
                "a": {"component_id": "comp1", "feature": "face", "feature_id": "plane_xy"},
                "b": {"component_id": "comp2", "feature": "face", "feature_id": "plane_xy"},
                "value": 10.0,
                "unit": "mm",
                "tolerance_plus": 0.1,
                "tolerance_minus": 0.05,
            },
        ]

        result = solve_assembly(components, mates, fixed_component_id="comp1")

        self.assertIn("tolerance_stackup", result)
        stackup = result["tolerance_stackup"]
        self.assertIn("mate1", stackup)
        self.assertEqual(stackup["mate1"]["nominal"], 10.0)
        self.assertEqual(stackup["mate1"]["worst_case"]["max"], 10.1)
        self.assertEqual(stackup["mate1"]["worst_case"]["min"], 9.95)


class TestMateTypes(unittest.TestCase):
    def test_parallel_mate(self):
        entities = [
            Entity(
                id="e1", entity_type="face", component_id="c1", feature_id="f1",
                position=(0.0, 0.0, 0.0), normal=(0.0, 0.0, 1.0)
            ),
            Entity(
                id="e2", entity_type="face", component_id="c2", feature_id="f1",
                position=(0.0, 0.0, 5.0), normal=(0.0, 0.0, -1.0)
            ),
        ]
        constraints = [
            MateConstraint(id="m1", mate_type="parallel", entity_a_id="e1", entity_b_id="e2"),
        ]

        solver = GeometricConstraintSolver(entities, constraints)
        result = solver.solve()

        self.assertTrue(result.solved)
        angle = vec3_angle(result.entities["e1"].normal, result.entities["e2"].normal)
        self.assertAlmostEqual(min(angle, math.pi - angle), 0.0, places=3)

    def test_perpendicular_mate(self):
        entities = [
            Entity(
                id="e1", entity_type="face", component_id="c1", feature_id="f1",
                position=(0.0, 0.0, 0.0), normal=(0.0, 0.0, 1.0)
            ),
            Entity(
                id="e2", entity_type="face", component_id="c2", feature_id="f1",
                position=(0.0, 0.0, 5.0), normal=(1.0, 0.0, 0.0)
            ),
        ]
        constraints = [
            MateConstraint(id="m1", mate_type="perpendicular", entity_a_id="e1", entity_b_id="e2"),
        ]

        solver = GeometricConstraintSolver(entities, constraints)
        result = solver.solve()

        self.assertTrue(result.solved)
        angle = vec3_angle(result.entities["e1"].normal, result.entities["e2"].normal)
        self.assertAlmostEqual(abs(angle - math.pi / 2), 0.0, places=3)

    def test_angle_mate_45_degrees(self):
        entities = [
            Entity(
                id="e1", entity_type="face", component_id="c1", feature_id="f1",
                position=(0.0, 0.0, 0.0), normal=(0.0, 0.0, 1.0)
            ),
            Entity(
                id="e2", entity_type="face", component_id="c2", feature_id="f1",
                position=(0.0, 5.0, 0.0), normal=(1.0, 0.0, 0.0)
            ),
        ]
        constraints = [
            MateConstraint(
                id="m1", mate_type="angle", entity_a_id="e1", entity_b_id="e2",
                value=45.0, unit="deg"
            ),
        ]

        solver = GeometricConstraintSolver(entities, constraints)
        result = solver.solve()

        self.assertIn("solved", result.__dict__)


if __name__ == "__main__":
    unittest.main()
