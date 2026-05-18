"""Slice 3: /billing/usage gains a non-breaking aggregated summary.

`_summarize_usage` is a pure function so it's unit-testable without a
DB: per-model rollup (sorted by cost desc) + a compute/storage/other
cost split. Storage = an event that moved bytes or whose kind names
storage; token/model events = compute.
"""
from kerf_billing.routes import _summarize_usage, _empty_summary


def _ev(**kw):
    base = {
        "kind": "chat", "model": None, "input_tokens": 0,
        "output_tokens": 0, "bytes_delta": 0, "usd_cost": 0.0,
    }
    base.update(kw)
    return base


def test_empty_events_is_empty_summary():
    assert _summarize_usage([]) == _empty_summary()
    assert _summarize_usage(None) == _empty_summary()


def test_by_model_groups_and_sorts_by_cost_desc():
    out = _summarize_usage([
        _ev(model="claude-opus-4-7", input_tokens=100, output_tokens=10, usd_cost=0.50),
        _ev(model="gpt-4o", input_tokens=200, output_tokens=20, usd_cost=2.00),
        _ev(model="claude-opus-4-7", input_tokens=50, output_tokens=5, usd_cost=0.25),
    ])
    rows = out["by_model"]
    assert [r["model"] for r in rows] == ["gpt-4o", "claude-opus-4-7"]
    opus = next(r for r in rows if r["model"] == "claude-opus-4-7")
    assert opus["input_tokens"] == 150
    assert opus["output_tokens"] == 15
    assert opus["usd_cost"] == 0.75
    assert opus["count"] == 2


def test_category_split_compute_vs_storage_vs_other():
    out = _summarize_usage([
        _ev(kind="chat", model="claude-opus-4-7", input_tokens=10, usd_cost=1.0),
        _ev(kind="storage", bytes_delta=1024, usd_cost=0.30),
        _ev(kind="render", bytes_delta=0, usd_cost=0.40),  # no tokens/model/storage → other
    ])
    cat = out["by_category"]
    assert cat["compute_usd"] == 1.0
    assert cat["storage_usd"] == 0.30
    assert cat["other_usd"] == 0.40
    assert round(cat["total_usd"], 2) == 1.70


def test_bytes_delta_forces_storage_even_without_storage_kind():
    out = _summarize_usage([_ev(kind="misc", bytes_delta=512, usd_cost=0.10)])
    assert out["by_category"]["storage_usd"] == 0.10
    assert out["by_category"]["compute_usd"] == 0.0


def test_none_cost_is_treated_as_zero_and_model_none_groups():
    out = _summarize_usage([
        _ev(model=None, kind="chat", input_tokens=5, usd_cost=None),
    ])
    assert out["by_category"]["total_usd"] == 0.0
    assert out["by_model"][0]["model"] is None
    assert out["by_model"][0]["count"] == 1


def test_empty_summary_shape():
    s = _empty_summary()
    assert s["by_model"] == []
    assert set(s["by_category"]) == {"compute_usd", "storage_usd", "other_usd", "total_usd"}
    assert all(v == 0.0 for v in s["by_category"].values())
