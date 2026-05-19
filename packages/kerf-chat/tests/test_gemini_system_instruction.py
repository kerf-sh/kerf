"""Regression: system_instruction on GeminiProvider goes to the model
CONSTRUCTOR, not generate_content().

google-generativeai ≥ 0.8 accepts `system_instruction` only on
`genai.GenerativeModel(name, system_instruction=...)`. Passing it to
`generate_content()` raises:
    TypeError: GenerativeModel.generate_content() got an unexpected
    keyword argument 'system_instruction'

That broke every Gemini chat call on dev. The friendly-error toast
surfaced as "The model returned an error. Try again, or pick a
different model." until we widened the error wrapper to include the
exception class name + message tail.

This test pins both halves of the contract:
  1. The constructor call carries system_instruction.
  2. generate_content() does NOT carry system_instruction.
"""
from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

from kerf_chat.llm import GeminiProvider, CompleteRequest


def _install_fake_genai():
    """Install a fake `google.generativeai` module that records the
    kwargs passed to GenerativeModel + generate_content."""
    captured: dict = {"ctor_kwargs": None, "gen_kwargs": None}

    class _Resp:
        candidates = []
        usage_metadata = types.SimpleNamespace(
            prompt_token_count=0, candidates_token_count=0
        )

    class _Model:
        def __init__(self, name, **kwargs):
            captured["ctor_kwargs"] = {"name": name, **kwargs}

        def generate_content(self, contents, **kwargs):
            captured["gen_kwargs"] = kwargs
            return _Resp()

    fake = types.ModuleType("google.generativeai")
    fake.configure = MagicMock()
    fake.GenerativeModel = _Model

    fake_types = types.ModuleType("google.generativeai.types")
    fake_types.GenerationConfig = lambda **kw: kw
    fake.types = fake_types

    # Put a parent `google` package in place too.
    google_pkg = types.ModuleType("google")
    google_pkg.generativeai = fake

    sys.modules["google"] = google_pkg
    sys.modules["google.generativeai"] = fake
    sys.modules["google.generativeai.types"] = fake_types

    return captured


def _restore_genai(saved: dict):
    for k in ("google", "google.generativeai", "google.generativeai.types"):
        if saved.get(k) is None:
            sys.modules.pop(k, None)
        else:
            sys.modules[k] = saved[k]


def test_system_instruction_goes_to_constructor_not_generate():
    saved = {
        k: sys.modules.get(k)
        for k in ("google", "google.generativeai", "google.generativeai.types")
    }
    captured = _install_fake_genai()
    try:
        provider = GeminiProvider(api_key="k")
        req = CompleteRequest(
            model="gemini-3-flash-preview",
            system="You are a CAD assistant.",
            messages=[],
        )
        provider.complete(req)
    finally:
        _restore_genai(saved)

    assert captured["ctor_kwargs"] is not None, "GenerativeModel was never instantiated"
    assert captured["ctor_kwargs"]["name"] == "gemini-3-flash-preview"
    assert captured["ctor_kwargs"]["system_instruction"] == "You are a CAD assistant.", (
        "system_instruction must be passed to the GenerativeModel constructor"
    )

    assert captured["gen_kwargs"] is not None, "generate_content was never called"
    assert "system_instruction" not in captured["gen_kwargs"], (
        "system_instruction must NOT be passed to generate_content()"
    )


def test_empty_system_omitted_from_constructor_kwarg_when_blank():
    """Don't pass system_instruction at all if the request has no system."""
    saved = {
        k: sys.modules.get(k)
        for k in ("google", "google.generativeai", "google.generativeai.types")
    }
    captured = _install_fake_genai()
    try:
        provider = GeminiProvider(api_key="k")
        req = CompleteRequest(
            model="gemini-3-flash-preview",
            system="",
            messages=[],
        )
        provider.complete(req)
    finally:
        _restore_genai(saved)

    # When system is blank, we still pass it (as None) to the ctor;
    # the SDK treats None as "no system". The contract we pin: it goes
    # on the constructor, NOT on generate_content.
    assert "system_instruction" not in (captured["gen_kwargs"] or {})
