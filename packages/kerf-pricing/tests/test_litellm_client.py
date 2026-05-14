"""Parse the LiteLLM JSON corpus into ParsedModel rows."""
from __future__ import annotations

import pytest

from kerf_pricing.litellm_client import (
    ParsedModel,
    _split_provider_model,
    _to_per_mtok,
    parse_models,
)


class TestParsing:
    def test_to_per_mtok_normal(self):
        # 3e-6 USD/tok → $3 / Mtok
        assert _to_per_mtok(0.000003) == pytest.approx(3.0)

    def test_to_per_mtok_zero(self):
        assert _to_per_mtok(0.0) == 0.0

    def test_to_per_mtok_none(self):
        assert _to_per_mtok(None) is None

    def test_to_per_mtok_string(self):
        assert _to_per_mtok("0.000003") == pytest.approx(3.0)

    def test_to_per_mtok_garbage(self):
        assert _to_per_mtok("not a number") is None

    def test_to_per_mtok_negative_dropped(self):
        # Negative price would corrupt our COGS math — drop silently
        assert _to_per_mtok(-1) is None

    def test_split_uses_explicit_provider(self):
        entry = {"litellm_provider": "anthropic"}
        provider, mid = _split_provider_model("claude-sonnet-4-7", entry)
        assert (provider, mid) == ("anthropic", "claude-sonnet-4-7")

    def test_split_falls_back_to_prefix(self):
        entry: dict = {}
        provider, mid = _split_provider_model("openai/gpt-4o", entry)
        assert (provider, mid) == ("openai", "gpt-4o")

    def test_split_prefers_explicit_over_prefix(self):
        # If the upstream maps it under "openai/foo" but tags it as
        # azure_ai, the explicit field wins.
        entry = {"litellm_provider": "azure_ai"}
        provider, mid = _split_provider_model("openai/foo", entry)
        assert provider == "azure_ai"
        assert mid == "foo"

    def test_split_bare_key_no_provider(self):
        # Some upstream entries are bare ("gpt-3.5-turbo") with no provider
        # field.  We return ("", key) and parse_models filters them out.
        entry: dict = {}
        provider, mid = _split_provider_model("some-model", entry)
        assert provider == ""
        assert mid == "some-model"

    def test_parse_filters_non_chat(self):
        raw = {
            "sample_spec": {"mode": "chat", "input_cost_per_token": 1, "output_cost_per_token": 1},
            "anthropic/claude-sonnet-4-7": {
                "mode": "chat",
                "litellm_provider": "anthropic",
                "input_cost_per_token": 0.000003,
                "output_cost_per_token": 0.000015,
            },
            "openai/text-embedding-3-small": {
                "mode": "embedding",
                "litellm_provider": "openai",
                "input_cost_per_token": 0.00000002,
            },
            "openai/dall-e-3": {
                "mode": "image_generation",
                "litellm_provider": "openai",
            },
            "openai/whisper-1": {
                "mode": "audio_transcription",
                "litellm_provider": "openai",
            },
        }
        parsed = parse_models(raw)
        ids = [(p.provider, p.model_id) for p in parsed]
        assert ("anthropic", "claude-sonnet-4-7") in ids
        # sample_spec is skipped even though mode=chat
        assert all(p.model_id != "sample_spec" for p in parsed)
        # Non-chat modes are filtered
        assert all("text-embedding-3-small" not in p.model_id for p in parsed)
        assert all("dall-e-3" not in p.model_id for p in parsed)

    def test_parse_drops_rows_missing_price(self):
        raw = {
            "broken-row": {
                "mode": "chat",
                "litellm_provider": "anthropic",
                "input_cost_per_token": 0.000003,
                # output_cost_per_token missing
            },
        }
        assert parse_models(raw) == []

    def test_parse_per_mtok_conversion(self):
        raw = {
            "anthropic/claude-sonnet-4-7": {
                "mode": "chat",
                "litellm_provider": "anthropic",
                "input_cost_per_token": 0.000003,
                "output_cost_per_token": 0.000015,
                "cache_read_input_token_cost": 0.0000003,
                "max_input_tokens": 200000,
            },
        }
        [m] = parse_models(raw)
        assert m.input_per_mtok == pytest.approx(3.0)
        assert m.output_per_mtok == pytest.approx(15.0)
        assert m.cache_read_per_mtok == pytest.approx(0.30)
        assert m.max_input_tokens == 200000

    def test_parse_handles_missing_cache_and_max(self):
        raw = {
            "openai/gpt-4o-mini": {
                "mode": "chat",
                "litellm_provider": "openai",
                "input_cost_per_token": 0.00000015,
                "output_cost_per_token": 0.0000006,
            },
        }
        [m] = parse_models(raw)
        assert m.cache_read_per_mtok is None
        assert m.max_input_tokens is None

    def test_parse_returns_dataclass_with_raw(self):
        raw = {
            "anthropic/claude-sonnet-4-7": {
                "mode": "chat",
                "litellm_provider": "anthropic",
                "input_cost_per_token": 0.000003,
                "output_cost_per_token": 0.000015,
            },
        }
        [m] = parse_models(raw)
        assert isinstance(m, ParsedModel)
        assert m.raw["mode"] == "chat"
