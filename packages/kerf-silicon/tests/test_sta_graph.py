"""test_sta_graph.py — pytest suite for kerf_silicon.sta.graph.

Run with::

    PYTHONPATH=packages/kerf-core/src:packages/kerf-silicon/src \\
        python3 -m pytest packages/kerf-silicon/tests/test_sta_graph.py -x
"""
from __future__ import annotations

import pathlib
import pytest

from kerf_silicon.liberty import parse as parse_liberty
from kerf_silicon.sta.graph import (
    NodeKind,
    TimingGraph,
    _nldm_interp,
    _interp_1d,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
INV1_LIB = FIXTURES / "inv_1.lib"

INV_CELL = "sky130_fd_sc_hd__inv_1"


@pytest.fixture(scope="module")
def inv_lib():
    return parse_liberty(INV1_LIB.read_text())


def _two_inv_netlist():
    """u1(INV) -> u2(INV): in_a -> net1 -> out_z."""
    return {
        "module": "two_inv",
        "ports": {
            "in_a": {"direction": "input"},
            "out_z": {"direction": "output"},
        },
        "instances": {
            "u1": {
                "cell": INV_CELL,
                "connections": {"A": "in_a", "Y": "net1"},
            },
            "u2": {
                "cell": INV_CELL,
                "connections": {"A": "net1", "Y": "out_z"},
            },
        },
    }


def _reconvergent_netlist():
    """
    Fan-out then reconvergent:
      in_a -> u1(INV) -> net1 -> u2(INV) -> net2
                      -> u3(INV) -> net3
      net2, net3 -> (two loads on out_z driven by u2 and u3, but
      we'll model it simply: u2 drives out_z, u3 drives out_w so
      we can observe max selection)
    """
    return {
        "module": "reconvergent",
        "ports": {
            "in_a": {"direction": "input"},
            "out_y": {"direction": "output"},
            "out_z": {"direction": "output"},
        },
        "instances": {
            "u1": {
                "cell": INV_CELL,
                "connections": {"A": "in_a", "Y": "net1"},
            },
            "u2": {
                "cell": INV_CELL,
                "connections": {"A": "net1", "Y": "out_y"},
            },
            "u3": {
                "cell": INV_CELL,
                "connections": {"A": "net1", "Y": "out_z"},
            },
        },
    }


# ---------------------------------------------------------------------------
# Tests: Node creation
# ---------------------------------------------------------------------------


class TestNodeCreation:
    def test_input_port_created(self, inv_lib):
        g = TimingGraph(_two_inv_netlist(), inv_lib)
        assert "in_a" in g.nodes
        assert g.nodes["in_a"].kind == NodeKind.INPUT_PORT

    def test_output_port_created(self, inv_lib):
        g = TimingGraph(_two_inv_netlist(), inv_lib)
        assert "out_z" in g.nodes
        assert g.nodes["out_z"].kind == NodeKind.OUTPUT_PORT

    def test_cell_in_nodes_created(self, inv_lib):
        g = TimingGraph(_two_inv_netlist(), inv_lib)
        assert "u1/A" in g.nodes
        assert g.nodes["u1/A"].kind == NodeKind.CELL_IN
        assert "u2/A" in g.nodes

    def test_cell_out_nodes_created(self, inv_lib):
        g = TimingGraph(_two_inv_netlist(), inv_lib)
        assert "u1/Y" in g.nodes
        assert g.nodes["u1/Y"].kind == NodeKind.CELL_OUT
        assert "u2/Y" in g.nodes

    def test_node_instance_and_pin(self, inv_lib):
        g = TimingGraph(_two_inv_netlist(), inv_lib)
        n = g.nodes["u1/A"]
        assert n.instance == "u1"
        assert n.pin == "A"


# ---------------------------------------------------------------------------
# Tests: Edges
# ---------------------------------------------------------------------------


class TestEdges:
    def test_net_edge_from_input_port_to_cell_in(self, inv_lib):
        g = TimingGraph(_two_inv_netlist(), inv_lib)
        # in_a -> u1/A (net edge, zero delay)
        srcs = {e.src for e in g.predecessors("u1/A")}
        assert "in_a" in srcs

    def test_internal_arc_cell_in_to_cell_out(self, inv_lib):
        g = TimingGraph(_two_inv_netlist(), inv_lib)
        # u1/A -> u1/Y (internal cell arc with positive delay)
        dsts = {e.dst for e in g.successors("u1/A")}
        assert "u1/Y" in dsts

    def test_internal_arc_delay_positive(self, inv_lib):
        g = TimingGraph(_two_inv_netlist(), inv_lib)
        arcs = [e for e in g.successors("u1/A") if e.dst == "u1/Y"]
        assert arcs
        assert arcs[0].delay > 0.0

    def test_net_edge_cell_out_to_next_cell_in(self, inv_lib):
        g = TimingGraph(_two_inv_netlist(), inv_lib)
        # u1/Y -> u2/A (net edge)
        dsts = {e.dst for e in g.successors("u1/Y")}
        assert "u2/A" in dsts

    def test_net_edge_cell_out_to_output_port(self, inv_lib):
        g = TimingGraph(_two_inv_netlist(), inv_lib)
        # u2/Y -> out_z
        dsts = {e.dst for e in g.successors("u2/Y")}
        assert "out_z" in dsts


# ---------------------------------------------------------------------------
# Tests: Topological sort
# ---------------------------------------------------------------------------


class TestTopologicalSort:
    def test_topo_order_length(self, inv_lib):
        g = TimingGraph(_two_inv_netlist(), inv_lib)
        order = g.topological_order()
        assert len(order) == len(g.nodes)

    def test_input_port_before_cell_in(self, inv_lib):
        g = TimingGraph(_two_inv_netlist(), inv_lib)
        order = g.topological_order()
        assert order.index("in_a") < order.index("u1/A")

    def test_cell_in_before_cell_out(self, inv_lib):
        g = TimingGraph(_two_inv_netlist(), inv_lib)
        order = g.topological_order()
        assert order.index("u1/A") < order.index("u1/Y")

    def test_cell_out_before_next_cell_in(self, inv_lib):
        g = TimingGraph(_two_inv_netlist(), inv_lib)
        order = g.topological_order()
        assert order.index("u1/Y") < order.index("u2/A")

    def test_cell_out_before_output_port(self, inv_lib):
        g = TimingGraph(_two_inv_netlist(), inv_lib)
        order = g.topological_order()
        assert order.index("u2/Y") < order.index("out_z")

    def test_reconvergent_topo_valid(self, inv_lib):
        g = TimingGraph(_reconvergent_netlist(), inv_lib)
        order = g.topological_order()
        assert len(order) == len(g.nodes)
        # u1 precedes both u2 and u3
        assert order.index("u1/Y") < order.index("u2/A")
        assert order.index("u1/Y") < order.index("u3/A")


# ---------------------------------------------------------------------------
# Tests: NLDM LUT interpolation
# ---------------------------------------------------------------------------


class TestNLDMInterp:
    """Corner-tap exact-match and bilinear interpolation tests."""

    # 2×2 table: idx1=[0.0, 1.0], idx2=[0.0, 1.0]
    # values = [v00, v01, v10, v11] = [1.0, 2.0, 3.0, 4.0]
    IDX1 = [0.0, 1.0]
    IDX2 = [0.0, 1.0]
    VALUES = [1.0, 2.0, 3.0, 4.0]

    def test_corner_00(self):
        v = _nldm_interp(self.VALUES, self.IDX1, self.IDX2, 2, 2, 0.0, 0.0)
        assert v == pytest.approx(1.0)

    def test_corner_01(self):
        v = _nldm_interp(self.VALUES, self.IDX1, self.IDX2, 2, 2, 0.0, 1.0)
        assert v == pytest.approx(2.0)

    def test_corner_10(self):
        v = _nldm_interp(self.VALUES, self.IDX1, self.IDX2, 2, 2, 1.0, 0.0)
        assert v == pytest.approx(3.0)

    def test_corner_11(self):
        v = _nldm_interp(self.VALUES, self.IDX1, self.IDX2, 2, 2, 1.0, 1.0)
        assert v == pytest.approx(4.0)

    def test_midpoint_bilinear(self):
        # mid-point should be (1+2+3+4)/4 = 2.5
        v = _nldm_interp(self.VALUES, self.IDX1, self.IDX2, 2, 2, 0.5, 0.5)
        assert v == pytest.approx(2.5)

    def test_extrapolation_clamped_low(self):
        # below axis range → clamp to corner
        v = _nldm_interp(self.VALUES, self.IDX1, self.IDX2, 2, 2, -1.0, -1.0)
        assert v == pytest.approx(1.0)  # corner 00

    def test_extrapolation_clamped_high(self):
        v = _nldm_interp(self.VALUES, self.IDX1, self.IDX2, 2, 2, 2.0, 2.0)
        assert v == pytest.approx(4.0)  # corner 11

    def test_empty_table_returns_zero(self):
        v = _nldm_interp([], [0.0, 1.0], [0.0, 1.0], 2, 2, 0.5, 0.5)
        assert v == pytest.approx(0.0)

    def test_3x3_table_corners_exact(self):
        """3×3 table from inv_1.lib fixture: all corner values match exactly."""
        # Use the 3×3 delay table from inv_1.lib:
        # idx1 = [0.01, 0.1, 0.5], idx2 = [0.001, 0.01, 0.1]
        # cell_rise values (row-major):
        #   0.100, 0.200, 0.300
        #   0.150, 0.250, 0.350
        #   0.200, 0.300, 0.400
        idx1 = [0.01, 0.1, 0.5]
        idx2 = [0.001, 0.01, 0.1]
        vals = [
            0.100, 0.200, 0.300,
            0.150, 0.250, 0.350,
            0.200, 0.300, 0.400,
        ]
        assert _nldm_interp(vals, idx1, idx2, 3, 3, 0.01, 0.001) == pytest.approx(0.100)
        assert _nldm_interp(vals, idx1, idx2, 3, 3, 0.01, 0.1) == pytest.approx(0.300)
        assert _nldm_interp(vals, idx1, idx2, 3, 3, 0.5, 0.001) == pytest.approx(0.200)
        assert _nldm_interp(vals, idx1, idx2, 3, 3, 0.5, 0.1) == pytest.approx(0.400)


# ---------------------------------------------------------------------------
# Tests: Endpoints / startpoints
# ---------------------------------------------------------------------------


class TestEndpointStartpoint:
    def test_output_port_is_endpoint(self, inv_lib):
        g = TimingGraph(_two_inv_netlist(), inv_lib)
        eps = g.endpoints()
        assert "out_z" in eps

    def test_input_port_is_startpoint(self, inv_lib):
        g = TimingGraph(_two_inv_netlist(), inv_lib)
        sps = g.startpoints()
        assert "in_a" in sps
