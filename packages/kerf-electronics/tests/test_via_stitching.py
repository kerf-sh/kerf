import json
import pytest
import importlib.util

spec = importlib.util.spec_from_file_location("via_stitching", "/Users/pc/code/exo/kerf/.claude/worktrees/agent-a32c4befabb8b2b49/kerf-electronics/src/kerf_electronics/tools/via_stitching.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

via_stitching = mod


def board():
    return {
        "pcb_board": {
            "width": 50,
            "height": 40,
            "pcb_trace": [],
            "pcb_pad": [],
            "pcb_via": [],
            "copper_pour": []
        }
    }


async def call(fn, **kwargs):
    result = await fn(None, json.dumps(kwargs).encode())
    data = json.loads(result)
    if isinstance(data, dict) and data.get('error'):
        raise Exception(data['error'])
    return data


class FakeCtx:
    pass


@pytest.mark.asyncio
async def test_add_via_stitching_grid():
    b = board()
    b["pcb_board"]["copper_pour"] = [{
        "pour_id": "pour1",
        "polygon": [{"x": 0, "y": 0}, {"x": 50, "y": 0}, {"x": 50, "y": 40}, {"x": 0, "y": 40}]
    }]
    r = await call(via_stitching.add_via_stitching,
                   circuit_json=b,
                   pour_id_or_polygon="pour1",
                   pitch_mm=5,
                   net_id="GND",
                   strategy="grid",
                   via_spec={"diameter": 0.8, "drill": 0.4})
    circuit = r["circuit_json"]
    assert "via_stitching" in circuit["pcb_board"]
    assert len(circuit["pcb_board"]["via_stitching"]) == 1
    assert circuit["pcb_board"]["via_stitching"][0]["strategy"] == "grid"


@pytest.mark.asyncio
async def test_add_via_stitching_perimeter():
    b = board()
    b["pcb_board"]["copper_pour"] = [{
        "pour_id": "pour1",
        "polygon": [{"x": 0, "y": 0}, {"x": 50, "y": 0}, {"x": 50, "y": 40}, {"x": 0, "y": 40}]
    }]
    r = await call(via_stitching.add_via_stitching,
                   circuit_json=b,
                   pour_id_or_polygon="pour1",
                   pitch_mm=5,
                   net_id="GND",
                   strategy="perimeter",
                   via_spec={"diameter": 0.8, "drill": 0.4})
    circuit = r["circuit_json"]
    vias = circuit["pcb_board"]["via_stitching"][0]["vias"]
    assert len(vias) > 0


@pytest.mark.asyncio
async def test_add_via_stitching_hex():
    b = board()
    b["pcb_board"]["copper_pour"] = [{
        "pour_id": "pour1",
        "polygon": [{"x": 0, "y": 0}, {"x": 50, "y": 0}, {"x": 50, "y": 40}, {"x": 0, "y": 40}]
    }]
    r = await call(via_stitching.add_via_stitching,
                   circuit_json=b,
                   pour_id_or_polygon="pour1",
                   pitch_mm=5,
                   net_id="GND",
                   strategy="hex",
                   via_spec={"diameter": 0.8, "drill": 0.4})
    circuit = r["circuit_json"]
    vias = circuit["pcb_board"]["via_stitching"][0]["vias"]
    assert len(vias) > 0


@pytest.mark.asyncio
async def test_add_via_stitching_polygon_direct():
    b = board()
    polygon = [{"x": 0, "y": 0}, {"x": 50, "y": 0}, {"x": 50, "y": 40}, {"x": 0, "y": 40}]
    r = await call(via_stitching.add_via_stitching,
                   circuit_json=b,
                   pour_id_or_polygon=polygon,
                   pitch_mm=5,
                   net_id="GND",
                   strategy="grid",
                   via_spec={"diameter": 0.8, "drill": 0.4})
    circuit = r["circuit_json"]
    assert len(circuit["pcb_board"]["via_stitching"]) == 1


@pytest.mark.asyncio
async def test_add_via_stitching_pour_not_found():
    b = board()
    try:
        r = await call(via_stitching.add_via_stitching,
                       circuit_json=b,
                       pour_id_or_polygon="nonexistent",
                       pitch_mm=5,
                       net_id="GND",
                       strategy="grid",
                       via_spec={"diameter": 0.8, "drill": 0.4})
        circuit = r.get("circuit_json", {})
    except Exception as e:
        assert "not found" in str(e).lower()


@pytest.mark.asyncio
async def test_remove_via_stitching():
    b = board()
    b["pcb_board"]["copper_pour"] = [{
        "pour_id": "pour1",
        "polygon": [{"x": 0, "y": 0}, {"x": 50, "y": 0}, {"x": 50, "y": 40}, {"x": 0, "y": 40}]
    }]
    r = await call(via_stitching.add_via_stitching,
                   circuit_json=b,
                   pour_id_or_polygon="pour1",
                   pitch_mm=5,
                   net_id="GND",
                   strategy="grid",
                   via_spec={"diameter": 0.8, "drill": 0.4})
    circuit = r["circuit_json"]
    assert len(circuit["pcb_board"]["via_stitching"]) == 1

    r2 = await call(via_stitching.remove_via_stitching, circuit_json=circuit, pour_id="pour1")
    circuit2 = r2["circuit_json"]
    assert len(circuit2["pcb_board"]["via_stitching"]) == 0


@pytest.mark.asyncio
async def test_apply_teardrops():
    b = board()
    b["pcb_board"]["pcb_trace"] = [{
        "pcb_trace_id": "trace1",
        "net_id": "GND",
        "route": [{"x": 5, "y": 5}, {"x": 15, "y": 5}],
        "width": 0.25
    }]
    b["pcb_board"]["pcb_pad"] = [{
        "pcb_pad_id": "pad1",
        "net_id": "GND",
        "x": 10,
        "y": 5,
        "width": 1.6
    }]
    r = await call(via_stitching.apply_teardrops, circuit_json=b, radius_factor=1.5)
    circuit = r["circuit_json"]
    assert "teardrops" in circuit["pcb_board"]
    assert len(circuit["pcb_board"]["teardrops"]) == 1


@pytest.mark.asyncio
async def test_apply_teardrops_via():
    b = board()
    b["pcb_board"]["pcb_trace"] = [{
        "pcb_trace_id": "trace1",
        "net_id": "GND",
        "route": [{"x": 5, "y": 5}, {"x": 15, "y": 5}],
        "width": 0.25
    }]
    b["pcb_board"]["pcb_via"] = [{
        "pcb_via_id": "via1",
        "net_id": "GND",
        "x": 10,
        "y": 5,
        "diameter": 0.8,
        "drill": 0.4
    }]
    r = await call(via_stitching.apply_teardrops, circuit_json=b, radius_factor=1.5)
    circuit = r["circuit_json"]
    assert len(circuit["pcb_board"]["teardrops"]) == 1


@pytest.mark.asyncio
async def test_apply_teardrops_preserves_original():
    b = board()
    b["pcb_board"]["pcb_trace"] = [{
        "pcb_trace_id": "trace1",
        "net_id": "GND",
        "route": [{"x": 5, "y": 5}, {"x": 15, "y": 5}],
        "width": 0.25
    }]
    b["pcb_board"]["pcb_pad"] = [{
        "pcb_pad_id": "pad1",
        "net_id": "GND",
        "x": 10,
        "y": 5,
        "width": 1.6
    }]
    original = json.dumps(b)
    await call(via_stitching.apply_teardrops, circuit_json=b, radius_factor=1.5)
    assert json.dumps(b) == original


def test_teardrop_path_points_numeric():
    pad = {"x": 10.0, "y": 10.0, "width": 1.6}
    trace = {"route": [{"x": 5, "y": 10}, {"x": 15, "y": 10}], "width": 0.25}
    path = mod._teardrop_for_pad_via(pad, trace, 1.5)
    assert path is not None
    assert len(path) == 3
    for pt in path:
        assert isinstance(pt['x'], (int, float))
        assert isinstance(pt['y'], (int, float))