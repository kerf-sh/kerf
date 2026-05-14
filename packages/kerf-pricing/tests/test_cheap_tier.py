"""Allow-list matching for cheap_tier_eligible."""
from __future__ import annotations

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
