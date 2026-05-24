"""Allow-list matching for cheap_tier_eligible."""
from __future__ import annotations

import pytest

from kerf_pricing.cheap_tier import CHEAP_TIER_ALLOWLIST, is_cheap_tier


class TestCheapTier:
    def test_anthropic_sonnet_4_7_eligible(self):
        assert is_cheap_tier("anthropic", "claude-sonnet-4-7")

    def test_anthropic_sonnet_4_6_eligible(self):
        assert is_cheap_tier("anthropic", "claude-sonnet-4-6")

    def test_anthropic_sonnet_dated_eligible(self):
        # Date-suffixed variants commonly published by Anthropic
        assert is_cheap_tier("anthropic", "claude-sonnet-4-7-20260101")
        assert is_cheap_tier("anthropic", "claude-sonnet-4-6-20251022")

    def test_anthropic_opus_not_eligible(self):
        assert not is_cheap_tier("anthropic", "claude-opus-4-7")

    def test_anthropic_haiku_not_eligible(self):
        # Haiku is genuinely cheap, but we DELIBERATELY kept it off the
        # free-tier list — we don't want to backstop API abuse with our
        # cheapest model.  Sonnet is the floor.
        assert not is_cheap_tier("anthropic", "claude-haiku-4-5")

    def test_google_gemini_3_flash_eligible(self):
        assert is_cheap_tier("google", "gemini-3-flash-preview")

    def test_google_gemini_2_flash_eligible(self):
        assert is_cheap_tier("google", "gemini-2-flash")

    def test_google_gemini_pro_not_eligible(self):
        assert not is_cheap_tier("google", "gemini-2.5-pro")

    def test_deepseek_v3_eligible(self):
        assert is_cheap_tier("deepseek", "deepseek-v3")

    def test_deepseek_chat_eligible(self):
        assert is_cheap_tier("deepseek", "deepseek-chat")

    def test_minimax_eligible(self):
        assert is_cheap_tier("minimax", "abab6.5-chat")
        assert is_cheap_tier("minimax", "MiniMax-Text-01")

    def test_openai_not_eligible(self):
        assert not is_cheap_tier("openai", "gpt-4o")
        assert not is_cheap_tier("openai", "gpt-4o-mini")

    def test_unknown_provider_not_eligible(self):
        assert not is_cheap_tier("acme-llm", "claude-sonnet-4-7")

    def test_empty_inputs_not_eligible(self):
        assert not is_cheap_tier("", "claude-sonnet-4-7")
        assert not is_cheap_tier("anthropic", "")
        assert not is_cheap_tier("", "")

    def test_allowlist_non_empty(self):
        assert len(CHEAP_TIER_ALLOWLIST) > 0


class TestCheapTierCatalogSnapshot:
    """Snapshot test: every entry in kerf_chat.CATALOG must agree with
    is_cheap_tier() — prevents silent drift between the two sources.

    T-402 R4: catalogue uses provider='gemini'; allowlist previously only
    had 'google'/'vertex_ai'.  Adding 'gemini' rows to CHEAP_TIER_ALLOWLIST
    (option a) means this test would have caught the regression at commit
    time.
    """

    def _catalog(self):
        from kerf_chat.llm import CATALOG  # type: ignore[import]
        return CATALOG

    def test_catalog_cheap_tier_flag_agrees_with_allowlist(self):
        """For every model in the kerf_chat CATALOG, the cheap_tier_eligible
        flag in the catalogue entry must match what is_cheap_tier() returns."""
        catalog = self._catalog()
        mismatches: list[str] = []
        for entry in catalog:
            provider = entry["provider"]
            model_id = entry["id"]
            flagged = entry.get("cheap_tier_eligible", False)
            computed = is_cheap_tier(provider, model_id)
            if flagged != computed:
                mismatches.append(
                    f"  provider={provider!r} model={model_id!r}: "
                    f"catalogue says cheap_tier_eligible={flagged}, "
                    f"is_cheap_tier() returned {computed}"
                )
        assert not mismatches, (
            "kerf_chat CATALOG and kerf_pricing CHEAP_TIER_ALLOWLIST are out of sync:\n"
            + "\n".join(mismatches)
            + "\n\nFix: update CHEAP_TIER_ALLOWLIST in cheap_tier.py OR correct "
            "cheap_tier_eligible flags in kerf_chat/llm.py CATALOG."
        )

    def test_catalog_has_cheap_tier_eligible_field(self):
        """All catalogue entries must explicitly declare cheap_tier_eligible."""
        catalog = self._catalog()
        missing = [
            f"provider={e['provider']!r} model={e['id']!r}"
            for e in catalog
            if "cheap_tier_eligible" not in e
        ]
        assert not missing, (
            "These CATALOG entries are missing 'cheap_tier_eligible':\n"
            + "\n".join(missing)
        )

    @pytest.mark.parametrize("model_id", [
        "gemini-3-flash-preview",
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
    ])
    def test_gemini_provider_flash_models_are_cheap_tier(self, model_id: str):
        """Flash models registered under provider='gemini' must pass the gate."""
        assert is_cheap_tier("gemini", model_id), (
            f"is_cheap_tier('gemini', {model_id!r}) returned False — "
            "free-tier users cannot access Gemini Flash"
        )

    @pytest.mark.parametrize("model_id", [
        "gemini-3-pro-preview",
        "gemini-2.5-pro",
    ])
    def test_gemini_provider_pro_models_are_not_cheap_tier(self, model_id: str):
        """Pro/heavy Gemini models must NOT be cheap-tier eligible."""
        assert not is_cheap_tier("gemini", model_id)
