import json
import unittest

from geom.dsn_writer import AutorouteParams, circuit_to_dsn, _build_layer_map
from geom.ses_reader import ses_to_routes, Route, Via, RoutingResult


class TestDsnWriter(unittest.TestCase):
    def test_build_layer_map_default(self):
        layer_map = _build_layer_map("1top,16bot")
        self.assertEqual(layer_map[1], "top")
        self.assertEqual(layer_map[16], "bot")

    def test_build_layer_map_four_layer(self):
        layer_map = _build_layer_map("1top,2mid1,3mid2,16bot")
        self.assertEqual(layer_map[1], "top")
        self.assertEqual(layer_map[2], "mid1")
        self.assertEqual(layer_map[3], "mid2")
        self.assertEqual(layer_map[16], "bot")

    def test_circuit_to_dsn_basic(self):
        circuit = {
            "board_outline": [[0, 0], [50, 0], [50, 40], [0, 40]],
            "components": [
                {"id": "U1", "footprint": "QFP32", "position": [10, 10], "rotation": 0},
                {"id": "U2", "footprint": "QFP32", "position": [30, 20], "rotation": 90},
            ],
            "nets": [
                {
                    "id": "net1",
                    "pins": [
                        {"component": "U1", "pin": 3},
                        {"component": "U2", "pin": 5},
                    ],
                },
            ],
        }

        params = AutorouteParams(
            trace_width_mm=0.2,
            via_diameter_mm=0.6,
            via_drill_mm=0.3,
            clearance_mm=0.2,
            routing_layers="1top,16bot",
        )

        dsn = circuit_to_dsn(circuit, params)

        self.assertIn("specctra_schema", dsn)
        self.assertIn("net net1", dsn)
        self.assertIn("component U1", dsn)
        self.assertIn("component U2", dsn)
        self.assertIn("polygon", dsn)

    def test_circuit_to_dsn_minimal(self):
        circuit = {
            "board_outline": [],
            "components": [],
            "nets": [],
        }

        dsn = circuit_to_dsn(circuit)
        self.assertIn("specctra_schema", dsn)
        self.assertIn("circuit", dsn)
        self.assertIn("library", dsn)


class TestSesReader(unittest.TestCase):
    def test_ses_to_routes_basic(self):
        ses = """
        (specctra_schema ses
          (wires 10)
          (vias 5)
          (nets 3)
          (unrouted 0)
          (net net1
            (pins U1.3 U2.5)
            (wire wire 1 (10000 10000) (15000 10000))
            (via via1 (15000 10000))
          )
          (net net2
            (pins U1.5 U3.2)
            (wire wire 1 (20000 20000) (25000 20000))
          )
        )
        """

        result = ses_to_routes(ses)

        self.assertIn("routes", result)
        self.assertIn("vias", result)
        self.assertEqual(result["nets_routed"], 3)
        self.assertEqual(result["nets_unrouted"], 0)
        self.assertEqual(result["segments_routed"], 10)
        self.assertEqual(result["vias_placed"], 5)

    def test_ses_to_routes_empty(self):
        ses = "(specctra_schema ses (nets 0) (unrouted 0))"
        result = ses_to_routes(ses)
        self.assertEqual(result["nets_routed"], 0)
        self.assertEqual(result["nets_unrouted"], 0)

    def test_ses_to_routes_unrouted(self):
        ses = "(specctra_schema ses (nets 5) (unrouted 2))"
        result = ses_to_routes(ses)
        self.assertEqual(result["nets_unrouted"], 2)
        self.assertEqual(result["nets_routed"], 3)


class TestAutorouteParams(unittest.TestCase):
    def test_default_params(self):
        params = AutorouteParams()
        self.assertEqual(params.trace_width_mm, 0.2)
        self.assertEqual(params.via_diameter_mm, 0.6)
        self.assertEqual(params.via_drill_mm, 0.3)
        self.assertEqual(params.clearance_mm, 0.2)
        self.assertEqual(params.routing_layers, "1top,16bot")
        self.assertEqual(params.cost_dihedral, 90)
        self.assertEqual(params.cost_via, 50)

    def test_custom_params(self):
        params = AutorouteParams(
            trace_width_mm=0.15,
            via_diameter_mm=0.5,
            via_drill_mm=0.25,
            clearance_mm=0.15,
            routing_layers="1top,2mid1,16bot",
            cost_dihedral=80,
            cost_via=40,
        )
        self.assertEqual(params.trace_width_mm, 0.15)
        self.assertEqual(params.via_diameter_mm, 0.5)
        self.assertEqual(params.routing_layers, "1top,2mid1,16bot")


if __name__ == "__main__":
    unittest.main()
