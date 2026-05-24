"""R16 — Every CATALOG entry must have an explicit paid_only bool field.

Verifies:
  - every catalogue entry declares paid_only as an explicit bool
  - expensive / high-capability models are flagged paid_only=True
  - cheap-tier-eligible models are NOT flagged paid_only=True
    (cheap models must be accessible on the free tier)
  - paid_only is a bool (not truthy str, None, int, etc.)
"""
from __future__ import annotations

import pytest
from kerf_chat.llm import CATALOG

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ids() -> set[str]:
    return {m["id"] for m in CATALOG}


# ---------------------------------------------------------------------------
# R16-A  Every entry has an explicit paid_only bool
# ---------------------------------------------------------------------------

def test_r16_every_catalog_entry_has_paid_only_bool():
    """paid_only must be present and a strict bool on every catalogue entry."""
    missing = []
    wrong_type = []
    for m in CATALOG:
        if "paid_only" not in m:
            missing.append(m["id"])
        elif not isinstance(m["paid_only"], bool):
            wrong_type.append((m["id"], type(m["paid_only"]).__name__))

    assert not missing, f"CATALOG entries missing paid_only field: {missing}"
    assert not wrong_type, (
        f"CATALOG entries with non-bool paid_only: {wrong_type}"
    )


# ---------------------------------------------------------------------------
# R16-B  Known expensive models are paid_only=True
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("model_id", [
    "gpt-4o",
    "o3-mini",
    "gemini-3-pro-preview",
    "kimi-k2-0905-preview",
    "claude-opus-4-7",
    "gemini-2.5-pro",
])
def test_r16_expensive_models_are_paid_only(model_id):
    """High-cost / flagship models must require a paid tier."""
    entry = next((m for m in CATALOG if m["id"] == model_id), None)
    assert entry is not None, f"{model_id} not found in CATALOG"
    assert entry["paid_only"] is True, (
        f"{model_id} should be paid_only=True (expensive model); got {entry['paid_only']}"
    )


# ---------------------------------------------------------------------------
# R16-C  cheap_tier_eligible=True implies paid_only=False
# ---------------------------------------------------------------------------

def test_r16_cheap_tier_eligible_models_are_not_paid_only():
    """A model eligible for the cheap tier must not also be paid_only=True.

    If a model is cheap-tier-eligible it must be usable on the free tier;
    marking it paid_only=True would contradict that.
    """
    conflicts = [
        m["id"]
        for m in CATALOG
        if m.get("cheap_tier_eligible") is True and m.get("paid_only") is True
    ]
    assert not conflicts, (
        f"Models cannot be both cheap_tier_eligible=True and paid_only=True: {conflicts}"
    )


# ---------------------------------------------------------------------------
# R16-D  Verify a few known free-accessible models are paid_only=False
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("model_id", [
    "claude-sonnet-4-6",
    "gemini-3-flash-preview",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
])
def test_r16_free_accessible_models_not_paid_only(model_id):
    entry = next((m for m in CATALOG if m["id"] == model_id), None)
    assert entry is not None, f"{model_id} not found in CATALOG"
    assert entry["paid_only"] is False, (
        f"{model_id} should be paid_only=False (free-accessible model); got {entry['paid_only']}"
    )
