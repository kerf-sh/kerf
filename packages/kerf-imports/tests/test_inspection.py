"""
Tests for inspection / model comparison.

Uses importlib pattern to load inspection.py directly,
testing the pure _compare_mesh_data function without DB/async.
"""
import importlib.util
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PLUGIN_ROOT = os.path.dirname(_HERE)
_TOOLS = os.path.join(_PLUGIN_ROOT, "src", "kerf_imports", "tools")


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_insp = _load_module("tools.inspection", os.path.join(_TOOLS, "inspection.py"))
_compare_mesh_data = _insp._compare_mesh_data


class TestCompareMeshData:
    def test_identical_meshes_return_zero_deviation(self):
        mesh = {"vertices": [[0, 0, 0], [1, 0, 0], [0, 1, 0]], "indices": [0, 1, 2]}
        result = _compare_mesh_data(mesh, mesh)
        assert result["summary"]["max_deviation"] == 0
        assert result["summary"]["mean_deviation"] == 0
        assert result["summary"]["percent_within_tolerance"] == 100

    def test_translated_mesh_returns_translation_distance(self):
        mesh_a = {"vertices": [[0, 0, 0], [100, 0, 0]], "indices": [0, 1]}
        mesh_b = {"vertices": [[0, 0, 5], [100, 0, 5]], "indices": [0, 1]}
        result = _compare_mesh_data(mesh_a, mesh_b)
        assert abs(result["summary"]["max_deviation"] - 5) < 0.001
        assert abs(result["summary"]["mean_deviation"] - 5) < 0.001

    def test_sampling_factor_reduces_computation(self):
        mesh_a = {"vertices": [[0, 0, 0], [1, 0, 0], [2, 0, 0], [3, 0, 0]], "indices": [0, 1, 2]}
        mesh_b = {"vertices": [[0, 0, 0], [1, 0, 0], [2, 0, 0], [3, 0, 0]], "indices": [0, 1, 2]}
        full = _compare_mesh_data(mesh_a, mesh_b)
        sampled = _compare_mesh_data(mesh_a, mesh_b, sampling=0.5)
        assert len(sampled["deviations"]) < len(full["deviations"])

    def test_tolerance_threshold_buckets_deviations(self):
        mesh_a = {"vertices": [[0, 0, 0], [0.05, 0, 0], [0.2, 0, 0]], "indices": [0, 1, 2]}
        mesh_b = {"vertices": [[0, 0, 0], [0, 0, 0], [0, 0, 0]], "indices": [0, 1, 2]}
        result = _compare_mesh_data(mesh_a, mesh_b, tolerance=0.1)
        assert abs(result["summary"]["percent_within_tolerance"] - 66.67) < 1

    def test_handles_empty_vertices(self):
        mesh_a = {"vertices": [], "indices": []}
        mesh_b = {"vertices": [[0, 0, 0]], "indices": [0]}
        result = _compare_mesh_data(mesh_a, mesh_b)
        assert result["summary"]["max_deviation"] == 0
        assert result["summary"]["percent_within_tolerance"] == 100

    def test_known_distance_3_4_5(self):
        mesh_a = {"vertices": [[0, 0, 0]], "indices": [0]}
        mesh_b = {"vertices": [[3, 4, 0]], "indices": [0]}
        result = _compare_mesh_data(mesh_a, mesh_b)
        assert abs(result["summary"]["max_deviation"] - 5) < 0.001

    def test_deviations_array_has_x_y_z_delta(self):
        mesh_a = {"vertices": [[1, 2, 3]], "indices": [0]}
        mesh_b = {"vertices": [[1, 2, 3]], "indices": [0]}
        result = _compare_mesh_data(mesh_a, mesh_b)
        d = result["deviations"][0]
        assert d["x"] == 1
        assert d["y"] == 2
        assert d["z"] == 3
        assert d["delta"] == 0

    def test_percent_within_tolerance_partial(self):
        mesh_a = {"vertices": [[0, 0, 0], [10, 0, 0]], "indices": [0, 1]}
        mesh_b = {"vertices": [[0, 0, 0], [0, 0, 0]], "indices": [0, 1]}
        result = _compare_mesh_data(mesh_a, mesh_b, tolerance=0.01)
        assert result["summary"]["percent_within_tolerance"] == 50

    def test_scaled_mesh_returns_scale_factor(self):
        mesh_a = {"vertices": [[1, 0, 0], [0, 1, 0]], "indices": [0, 1]}
        mesh_b = {"vertices": [[2, 0, 0], [0, 2, 0]], "indices": [0, 1]}
        result = _compare_mesh_data(mesh_a, mesh_b)
        assert abs(result["summary"]["max_deviation"] - 1) < 0.1

    def test_large_mesh_performance(self):
        verts = [[i * 0.01, 0, 0] for i in range(100)]
        mesh_a = {"vertices": verts, "indices": []}
        mesh_b = {"vertices": [[v[0], 0.001, 0] for v in verts], "indices": []}
        result = _compare_mesh_data(mesh_a, mesh_b, tolerance=0.01)
        assert result["summary"]["max_deviation"] > 0
        assert len(result["deviations"]) == 100

    def test_default_tolerance_is_point_one(self):
        mesh = {"vertices": [[0, 0, 0]], "indices": [0]}
        result = _compare_mesh_data(mesh, mesh)
        assert result["summary"]["max_deviation"] == 0

    def test_sampling_default_is_one(self):
        mesh_a = {"vertices": [[0, 0, 0], [1, 0, 0]], "indices": [0, 1]}
        mesh_b = {"vertices": [[0, 0, 0], [1, 0, 0]], "indices": [0, 1]}
        result = _compare_mesh_data(mesh_a, mesh_b)
        assert len(result["deviations"]) == 2

    def test_mirrored_mesh_has_symmetric_deviation(self):
        mesh_a = {"vertices": [[1, 0, 0], [0, 1, 0]], "indices": [0, 1]}
        mesh_b = {"vertices": [[-1, 0, 0], [0, -1, 0]], "indices": [0, 1]}
        result = _compare_mesh_data(mesh_a, mesh_b)
        assert result["summary"]["max_deviation"] > 0