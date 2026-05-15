"""Hermetic tests for the `author` phase with a MOCKED LLM.

No network, no live LLM, no API key. We inject ``llm_call`` so the test
fully controls what the "LLM" returns and asserts the bounded-repair token
model (1 author call + at most 2 repairs, then FAILED — never unbounded).
"""

import os

import pytest

from kerf_partsgen import kernel
from kerf_partsgen.author import MAX_REPAIRS, author_family

needs_kernel = pytest.mark.skipif(
    not kernel.KERNEL_AVAILABLE,
    reason="no OCCT kernel binding (cadquery/pythonocc) installed",
)

_GOOD_MODULE = '''
from kerf_partsgen import kernel
FAMILY = {"family_id": "mock_fam", "name": "Mock", "standard": "MOCK",
          "domain": "mechanical", "category": "mechanical/test", "units": "mm"}
SIZES = [{"size": "A", "params": {"d": 10.0, "h": 4.0},
          "expect": {"bbox_mm": [10.0, 10.0, 4.0], "volume_mm3": None}}]
def build(row):
    p = row["params"]
    return kernel.cylinder(p["d"] / 2.0, p["h"])
'''

# Declares a wildly-wrong bbox so it fails the gate (drives the repair loop).
_BAD_MODULE = '''
from kerf_partsgen import kernel
FAMILY = {"family_id": "mock_fam", "name": "Mock", "standard": "MOCK",
          "domain": "mechanical", "category": "mechanical/test", "units": "mm"}
SIZES = [{"size": "A", "params": {"d": 10.0, "h": 4.0},
          "expect": {"bbox_mm": [999.0, 999.0, 999.0], "volume_mm3": 1e9}}]
def build(row):
    p = row["params"]
    return kernel.cylinder(p["d"] / 2.0, p["h"])
'''


def test_author_requires_a_key_and_never_calls_llm_without_one(tmp_path):
    calls = []

    def spy(system, user, model, api_key):
        calls.append(user)
        return _GOOD_MODULE

    out = author_family(
        "mock_fam", "Mock fam", "MOCK", str(tmp_path),
        gen_dir=str(tmp_path), api_key="", llm_call=spy,
    )
    assert out.status == "FAILED"
    assert out.attempts == 0
    assert calls == []  # no key → zero LLM calls, zero tokens


@needs_kernel
def test_author_success_is_one_llm_call(tmp_path):
    calls = []

    def fake_llm(system, user, model, api_key):
        calls.append(user)
        return "```python\n" + _GOOD_MODULE + "\n```"

    out = author_family(
        "mock_fam", "Mock fam", "MOCK", str(tmp_path),
        gen_dir=str(tmp_path), api_key="test-key", llm_call=fake_llm,
    )
    assert out.status == "AUTHORED"
    assert out.attempts == 1               # exactly one call on clean success
    assert len(calls) == 1
    assert os.path.isfile(out.generator_path)


@needs_kernel
def test_author_repairs_then_succeeds_within_budget(tmp_path):
    seq = [_BAD_MODULE, _BAD_MODULE, _GOOD_MODULE]
    calls = []

    def fake_llm(system, user, model, api_key):
        calls.append(user)
        return seq[len(calls) - 1]

    out = author_family(
        "mock_fam", "Mock fam", "MOCK", str(tmp_path),
        gen_dir=str(tmp_path), api_key="test-key", llm_call=fake_llm,
    )
    assert out.status == "AUTHORED"
    assert out.attempts == 3               # 1 author + 2 repairs == budget
    # the repair prompts carried the gate failure back to the model
    assert "FAILED THE LOCAL VERIFICATION GATE" in calls[1]


@needs_kernel
def test_author_is_bounded_and_marks_failed(tmp_path):
    calls = []

    def always_bad(system, user, model, api_key):
        calls.append(user)
        return _BAD_MODULE

    out = author_family(
        "mock_fam", "Mock fam", "MOCK", str(tmp_path),
        gen_dir=str(tmp_path), api_key="test-key", llm_call=always_bad,
    )
    assert out.status == "FAILED"
    # NEVER an unbounded loop: exactly 1 + MAX_REPAIRS calls, then stop.
    assert out.attempts == 1 + MAX_REPAIRS
    assert len(calls) == 1 + MAX_REPAIRS
    assert not os.path.isfile(out.generator_path)
