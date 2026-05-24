"""Curated allow-list of cheap-tier-eligible chat models.

Anything matching one of these (provider, model_id_glob) tuples is flagged
``cheap_tier_eligible=True`` in the ``model_prices`` table at refresh time.
Free-tier quota can ONLY be redeemed against these models.

The glob is fnmatch-style.  Provider is matched exactly.
"""
from __future__ import annotations

import fnmatch

# (provider, model_id_glob)
CHEAP_TIER_ALLOWLIST: list[tuple[str, str]] = [
    # Anthropic
    ("anthropic", "claude-sonnet-4-7"),
    ("anthropic", "claude-sonnet-4-7-*"),
    ("anthropic", "claude-sonnet-4-6"),
    ("anthropic", "claude-sonnet-4-6-*"),
    # Google — legacy LiteLLM provider keys and Vertex AI
    ("google", "gemini-3-flash-preview"),
    ("google", "gemini-3-flash-*"),
    ("google", "gemini-2-flash"),
    ("google", "gemini-2-flash-*"),
    ("google", "gemini/gemini-3-flash*"),
    ("google", "gemini/gemini-2-flash*"),
    ("vertex_ai", "gemini-3-flash*"),
    ("vertex_ai", "gemini-2-flash*"),
    # Gemini — kerf_chat catalogue provider key (provider="gemini").
    # Kept as additive rows (option a) rather than renaming the catalogue to
    # "google" because DB rows and any existing telemetry already store
    # provider='gemini'; renaming would break joins without a migration.
    ("gemini", "gemini-3-flash-preview"),
    ("gemini", "gemini-3-flash-*"),
    ("gemini", "gemini-2-flash"),
    ("gemini", "gemini-2-flash-*"),
    ("gemini", "gemini-2.5-flash"),
    ("gemini", "gemini-2.5-flash-*"),
    ("gemini", "gemini-2.5-flash-lite"),
    ("gemini", "gemini-2.5-flash-lite-*"),
    # DeepSeek
    ("deepseek", "deepseek-v3"),
    ("deepseek", "deepseek-v3-*"),
    ("deepseek", "deepseek-chat"),
    ("deepseek", "deepseek/deepseek-v3*"),
    ("deepseek", "deepseek/deepseek-chat*"),
    # MiniMax
    ("minimax", "abab6.5-chat"),
    ("minimax", "abab6.5-chat-*"),
    ("minimax", "MiniMax-Text-01"),
    ("minimax", "MiniMax-Text-01-*"),
]


def is_cheap_tier(provider: str, model_id: str) -> bool:
    """True iff (provider, model_id) matches an entry in the allow-list."""
    if not provider or not model_id:
        return False
    for allowed_provider, glob in CHEAP_TIER_ALLOWLIST:
        if provider != allowed_provider:
            continue
        if fnmatch.fnmatchcase(model_id, glob):
            return True
    return False
