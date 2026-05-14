"""Tests for kerf_core.utils.topo_sort."""
import pytest

from kerf_core.utils.topo_sort import topo_sort


def test_no_deps_returns_input():
    nodes = ["a", "b", "c"]
    order = topo_sort(nodes, {})
    assert sorted(order) == sorted(nodes)


def test_simple_chain():
    order = topo_sort(["c", "a", "b"], {"c": ["b"], "b": ["a"]})
    assert order.index("a") < order.index("b") < order.index("c")


def test_diamond():
    order = topo_sort(["a", "b", "c", "d"], {"d": ["b", "c"], "b": ["a"], "c": ["a"]})
    assert order.index("a") < order.index("b")
    assert order.index("a") < order.index("c")
    assert order.index("b") < order.index("d")
    assert order.index("c") < order.index("d")


def test_cycle_raises():
    with pytest.raises(ValueError, match="cycle"):
        topo_sort(["a", "b"], {"a": ["b"], "b": ["a"]})
