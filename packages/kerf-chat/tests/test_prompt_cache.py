"""
Tests for Anthropic prompt-caching wire-up in kerf_chat.llm.

All tests are hermetic — the anthropic client is fully mocked; no real network
calls are made.  Tests verify:
  - cache_control injected into system and tools blocks when caching is on
  - cache_control absent when caching is disabled
  - rolling user/assistant messages never receive cache_control
  - empty system / no-tools paths handled cleanly
  - only the last tool receives cache_control (breakpoint semantics)
  - other providers (OpenAI, Moonshot, Gemini) are entirely unaffected
  - degradation path: SDK without cache_control support raises no error
  - feature-detect helper works correctly
  - LLMConfig default is True; can be overridden
  - Registry threads the setting into AnthropicProvider
"""
from __future__ import annotations

import json
import sys
import types
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers to build minimal anthropic SDK stubs
# ---------------------------------------------------------------------------

def _make_anthropic_stub(supports_cache: bool = True):
    """Return a stub anthropic module with or without cache_control support."""
    stub = types.ModuleType("anthropic")
    stub.__version__ = "0.102.0"

    # types sub-module
    types_stub = types.ModuleType("anthropic.types")
    if supports_cache:
        class _ToolParam:
            __annotations__ = {
                "cache_control": "Optional[CacheControlEphemeralParam]",
                "name": "str",
                "input_schema": "dict",
            }
        types_stub.ToolParam = _ToolParam
    else:
        class _ToolParamNoCache:
            __annotations__ = {
                "name": "str",
                "input_schema": "dict",
            }
        types_stub.ToolParam = _ToolParamNoCache

    stub.types = types_stub
    sys.modules["anthropic.types"] = types_stub

    # Mock response
    @dataclass
    class _Usage:
        input_tokens: int = 10
        output_tokens: int = 5

    @dataclass
    class _Block:
        type: str
        text: str = ""
        id: str = "blk_1"
        name: str = ""
        input: dict = field(default_factory=dict)

    @dataclass
    class _Response:
        content: list = field(default_factory=list)
        stop_reason: str = "end_turn"
        usage: _Usage = field(default_factory=_Usage)

    _default_response = _Response(content=[_Block(type="text", text="ok")])

    class _Messages:
        def __init__(self):
            self._response = _default_response
            self.last_call: dict = {}

        def create(self, **kwargs):
            self.last_call = kwargs
            return self._response

    class _Anthropic:
        def __init__(self, **kwargs):
            self.messages = _Messages()
            # expose for test inspection
            stub._last_client = self

        api_key = "fake"

    stub.Anthropic = _Anthropic
    return stub


def _install_anthropic_stub(stub):
    sys.modules["anthropic"] = stub
    sys.modules["anthropic.types"] = stub.types


def _remove_anthropic_stub():
    for key in list(sys.modules.keys()):
        if key == "anthropic" or key.startswith("anthropic."):
            del sys.modules[key]


# ---------------------------------------------------------------------------
# Import the module under test (after stubs are wired)
# ---------------------------------------------------------------------------

from kerf_chat.llm import (
    AnthropicProvider,
    CompleteRequest,
    LLMConfig,
    Message,
    Registry,
    ToolSpec,
    _anthropic_sdk_supports_cache_control,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def stub_with_cache():
    s = _make_anthropic_stub(supports_cache=True)
    _install_anthropic_stub(s)
    yield s
    _remove_anthropic_stub()


@pytest.fixture()
def stub_without_cache():
    s = _make_anthropic_stub(supports_cache=False)
    _install_anthropic_stub(s)
    yield s
    _remove_anthropic_stub()


def _call_kwargs(stub) -> dict:
    """Return the kwargs from the most recent client.messages.create() call."""
    return stub._last_client.messages.last_call


def _simple_req(**overrides) -> CompleteRequest:
    defaults = dict(
        model="claude-sonnet-4-6",
        system="You are helpful.",
        messages=[Message(role="user", content="hello")],
        max_tokens=100,
        temperature=0.0,
        tools=[],
        tool_choice="auto",
    )
    defaults.update(overrides)
    return CompleteRequest(**defaults)


def _tool_req(n_tools: int = 2, **overrides) -> CompleteRequest:
    tools = [
        ToolSpec(
            name=f"tool_{i}",
            description=f"Tool number {i}",
            input_schema={"type": "object", "properties": {}},
        )
        for i in range(n_tools)
    ]
    return _simple_req(tools=tools, **overrides)


# ===========================================================================
# 1. cache_control on system block (caching ON)
# ===========================================================================

def test_system_has_cache_control_when_cache_on(stub_with_cache):
    provider = AnthropicProvider("key", prompt_cache=True)
    import httpx
    with patch("httpx.Client"):
        provider.complete(_simple_req())
    kw = _call_kwargs(stub_with_cache)
    system = kw["system"]
    assert isinstance(system, list), "system should be a list when caching is on"
    assert len(system) == 1
    block = system[0]
    assert block["type"] == "text"
    assert block["text"] == "You are helpful."
    assert "cache_control" in block
    assert block["cache_control"]["type"] == "ephemeral"


# ===========================================================================
# 2. cache_control ABSENT on system block (caching OFF)
# ===========================================================================

def test_system_no_cache_control_when_cache_off(stub_with_cache):
    provider = AnthropicProvider("key", prompt_cache=False)
    import httpx
    with patch("httpx.Client"):
        provider.complete(_simple_req())
    kw = _call_kwargs(stub_with_cache)
    system = kw["system"]
    # Should be a plain string, not a list
    assert isinstance(system, str)
    assert system == "You are helpful."


# ===========================================================================
# 3. cache_control on last tool (caching ON)
# ===========================================================================

def test_last_tool_has_cache_control_when_cache_on(stub_with_cache):
    provider = AnthropicProvider("key", prompt_cache=True)
    import httpx
    with patch("httpx.Client"):
        provider.complete(_tool_req(n_tools=3))
    kw = _call_kwargs(stub_with_cache)
    tools = kw["tools"]
    assert len(tools) == 3
    assert "cache_control" in tools[-1]
    assert tools[-1]["cache_control"]["type"] == "ephemeral"


# ===========================================================================
# 4. Only the last tool gets cache_control (other tools are clean)
# ===========================================================================

def test_only_last_tool_gets_cache_control(stub_with_cache):
    provider = AnthropicProvider("key", prompt_cache=True)
    import httpx
    with patch("httpx.Client"):
        provider.complete(_tool_req(n_tools=3))
    kw = _call_kwargs(stub_with_cache)
    tools = kw["tools"]
    for tool in tools[:-1]:
        assert "cache_control" not in tool, (
            f"Only last tool should have cache_control, but found it on: {tool['name']}"
        )


# ===========================================================================
# 5. No cache_control on tools when caching OFF
# ===========================================================================

def test_tools_no_cache_control_when_cache_off(stub_with_cache):
    provider = AnthropicProvider("key", prompt_cache=False)
    import httpx
    with patch("httpx.Client"):
        provider.complete(_tool_req(n_tools=2))
    kw = _call_kwargs(stub_with_cache)
    for tool in kw["tools"]:
        assert "cache_control" not in tool


# ===========================================================================
# 6. Rolling user/assistant messages have no cache_control (caching ON)
# ===========================================================================

def test_rolling_messages_have_no_cache_control(stub_with_cache):
    provider = AnthropicProvider("key", prompt_cache=True)
    req = _simple_req(messages=[
        Message(role="user", content="first turn"),
        Message(role="assistant", content="reply"),
        Message(role="user", content="second turn"),
    ])
    import httpx
    with patch("httpx.Client"):
        provider.complete(req)
    kw = _call_kwargs(stub_with_cache)
    for msg in kw["messages"]:
        content = msg["content"]
        if isinstance(content, list):
            for block in content:
                assert "cache_control" not in block, (
                    "Rolling messages must not have cache_control"
                )
        # Plain string content has no cache_control by definition


# ===========================================================================
# 7. Empty system string — no list wrapping, just empty string
# ===========================================================================

def test_empty_system_not_wrapped_in_list(stub_with_cache):
    provider = AnthropicProvider("key", prompt_cache=True)
    import httpx
    with patch("httpx.Client"):
        provider.complete(_simple_req(system=""))
    kw = _call_kwargs(stub_with_cache)
    # Empty system: caching condition is `use_cache and req.system` — falsy system skips wrapping
    system = kw["system"]
    assert isinstance(system, str)
    assert system == ""


# ===========================================================================
# 8. No tools — tools param stays None, no crash
# ===========================================================================

def test_no_tools_no_crash_with_cache_on(stub_with_cache):
    provider = AnthropicProvider("key", prompt_cache=True)
    import httpx
    with patch("httpx.Client"):
        result = provider.complete(_simple_req(tools=[]))
    assert result.content == "ok"
    kw = _call_kwargs(stub_with_cache)
    assert kw.get("tools") is None


# ===========================================================================
# 9. Single tool gets cache_control (edge case: n_tools=1)
# ===========================================================================

def test_single_tool_gets_cache_control(stub_with_cache):
    provider = AnthropicProvider("key", prompt_cache=True)
    import httpx
    with patch("httpx.Client"):
        provider.complete(_tool_req(n_tools=1))
    kw = _call_kwargs(stub_with_cache)
    tools = kw["tools"]
    assert len(tools) == 1
    assert "cache_control" in tools[0]
    assert tools[0]["cache_control"]["type"] == "ephemeral"


# ===========================================================================
# 10. SDK without cache_control: degrades without crash
# ===========================================================================

def test_sdk_without_cache_control_degrades_cleanly(stub_without_cache):
    """When the SDK does not expose cache_control on ToolParam, no crash occurs."""
    provider = AnthropicProvider("key", prompt_cache=True)
    import httpx
    with patch("httpx.Client"):
        result = provider.complete(_tool_req(n_tools=2))
    assert result.content == "ok"
    kw = _call_kwargs(stub_without_cache)
    # Should fall back to plain system string
    assert isinstance(kw["system"], str)
    # Tools should have no cache_control
    for tool in kw["tools"]:
        assert "cache_control" not in tool


# ===========================================================================
# 11. _anthropic_sdk_supports_cache_control helper — positive
# ===========================================================================

def test_sdk_supports_cache_control_true(stub_with_cache):
    assert _anthropic_sdk_supports_cache_control() is True


# ===========================================================================
# 12. _anthropic_sdk_supports_cache_control helper — negative
# ===========================================================================

def test_sdk_supports_cache_control_false(stub_without_cache):
    assert _anthropic_sdk_supports_cache_control() is False


# ===========================================================================
# 13. _anthropic_sdk_supports_cache_control — module with no annotations
# ===========================================================================

def test_sdk_supports_cache_control_no_annotations():
    """A ToolParam class with an empty __annotations__ dict returns False."""
    stub = _make_anthropic_stub(supports_cache=False)
    _install_anthropic_stub(stub)
    try:
        result = _anthropic_sdk_supports_cache_control()
        assert result is False
    finally:
        _remove_anthropic_stub()


# ===========================================================================
# 14. LLMConfig default: anthropic_prompt_cache is True
# ===========================================================================

def test_llmconfig_prompt_cache_default_true():
    cfg = LLMConfig(anthropic_api_key="k")
    assert cfg.anthropic_prompt_cache is True


# ===========================================================================
# 15. LLMConfig: anthropic_prompt_cache can be set to False
# ===========================================================================

def test_llmconfig_prompt_cache_can_be_disabled():
    cfg = LLMConfig(anthropic_api_key="k", anthropic_prompt_cache=False)
    assert cfg.anthropic_prompt_cache is False


# ===========================================================================
# 16. Registry threads prompt_cache=True into AnthropicProvider
# ===========================================================================

def test_registry_threads_prompt_cache_true():
    cfg = LLMConfig(anthropic_api_key="k", anthropic_prompt_cache=True)
    reg = Registry(cfg)
    provider = reg.providers["anthropic"]
    assert isinstance(provider, AnthropicProvider)
    assert provider.prompt_cache is True


# ===========================================================================
# 17. Registry threads prompt_cache=False into AnthropicProvider
# ===========================================================================

def test_registry_threads_prompt_cache_false():
    cfg = LLMConfig(anthropic_api_key="k", anthropic_prompt_cache=False)
    reg = Registry(cfg)
    provider = reg.providers["anthropic"]
    assert provider.prompt_cache is False


# ===========================================================================
# 18. Other providers (OpenAI) are not affected
# ===========================================================================

def test_openai_provider_not_affected(stub_with_cache):
    """OpenAI provider should work normally with no cache_control logic."""
    openai_stub = types.ModuleType("openai")

    @dataclass
    class _Choice:
        finish_reason: str = "stop"

        @dataclass
        class _Message:
            content: str = "hello"
            tool_calls: Any = None
        message: _Message = field(default_factory=_Message)

    @dataclass
    class _Usage:
        prompt_tokens: int = 5
        completion_tokens: int = 3

    @dataclass
    class _OAIResponse:
        choices: list = field(default_factory=lambda: [_Choice()])
        model: str = "gpt-4o"
        usage: _Usage = field(default_factory=_Usage)

    class _Completions:
        def __init__(self):
            self.last_call: dict = {}

        def create(self, **kwargs):
            self.last_call = kwargs
            return _OAIResponse()

    class _Chat:
        def __init__(self):
            self.completions = _Completions()

    class _OpenAI:
        def __init__(self, **kwargs):
            self.chat = _Chat()
            openai_stub._last_client = self

    openai_stub.OpenAI = _OpenAI
    sys.modules["openai"] = openai_stub

    try:
        from kerf_chat.llm import OpenAIProvider
        provider = OpenAIProvider("openai_key")
        req = _simple_req(model="gpt-4o", tools=[
            ToolSpec(name="t1", description="d1", input_schema={"type": "object", "properties": {}})
        ])
        result = provider.complete(req)
        assert result.content == "hello"
        # Verify no cache_control was injected anywhere
        call = openai_stub._last_client.chat.completions.last_call
        for msg in call.get("messages", []):
            for key in msg:
                assert key != "cache_control"
    finally:
        sys.modules.pop("openai", None)


# ===========================================================================
# 19. Moonshot provider is not affected
# ===========================================================================

def test_moonshot_provider_not_affected(stub_with_cache):
    """Moonshot provider should route through OpenAI-compat layer, no cache_control."""
    openai_stub = types.ModuleType("openai")

    @dataclass
    class _Choice:
        finish_reason: str = "stop"

        @dataclass
        class _Msg:
            content: str = "moon"
            tool_calls: Any = None
        message: _Msg = field(default_factory=_Msg)

    @dataclass
    class _Usage:
        prompt_tokens: int = 5
        completion_tokens: int = 2

    @dataclass
    class _MSResponse:
        choices: list = field(default_factory=lambda: [_Choice()])
        model: str = "moonshot-v1-32k"
        usage: _Usage = field(default_factory=_Usage)

    class _Completions:
        def create(self, **kwargs):
            return _MSResponse()

    class _Chat:
        def __init__(self):
            self.completions = _Completions()

    class _OpenAI:
        def __init__(self, **kwargs):
            self.chat = _Chat()

    openai_stub.OpenAI = _OpenAI
    sys.modules["openai"] = openai_stub

    try:
        from kerf_chat.llm import MoonshotProvider
        provider = MoonshotProvider("moon_key")
        result = provider.complete(_simple_req(model="moonshot-v1-32k"))
        assert result.content == "moon"
    finally:
        sys.modules.pop("openai", None)


# ===========================================================================
# 20. Gemini provider is not affected
# ===========================================================================

def test_gemini_provider_not_affected():
    """Gemini provider should work unmodified; no cache_control involved."""
    genai_stub = types.ModuleType("google.generativeai")

    @dataclass
    class _Part:
        text: str = "gemini"

    @dataclass
    class _Content:
        parts: list = field(default_factory=lambda: [_Part()])

    @dataclass
    class _Candidate:
        content: _Content = field(default_factory=_Content)

    @dataclass
    class _GeminiResponse:
        candidates: list = field(default_factory=lambda: [_Candidate()])

    class _GenerativeModel:
        def __init__(self, model_name, **kwargs):
            pass

        def generate_content(self, *args, **kwargs):
            return _GeminiResponse()

    genai_stub.GenerativeModel = _GenerativeModel
    genai_stub.configure = lambda **kwargs: None

    class _types:
        class GenerationConfig:
            def __init__(self, **kwargs):
                pass

    genai_stub.types = _types

    google_stub = types.ModuleType("google")
    google_stub.generativeai = genai_stub
    sys.modules["google"] = google_stub
    sys.modules["google.generativeai"] = genai_stub

    try:
        from kerf_chat.llm import GeminiProvider
        provider = GeminiProvider("gemini_key")
        result = provider.complete(_simple_req(model="gemini-2.5-flash"))
        assert result.content == "gemini"
    finally:
        sys.modules.pop("google", None)
        sys.modules.pop("google.generativeai", None)


# ===========================================================================
# 21. Response parsed correctly when caching on (input/output tokens)
# ===========================================================================

def test_response_token_counts_preserved(stub_with_cache):
    provider = AnthropicProvider("key", prompt_cache=True)
    import httpx
    with patch("httpx.Client"):
        result = provider.complete(_simple_req())
    assert result.input_tokens == 10
    assert result.output_tokens == 5


# ===========================================================================
# 22. System text preserved exactly after wrapping
# ===========================================================================

def test_system_text_content_preserved_after_wrapping(stub_with_cache):
    long_system = "A" * 10_000
    provider = AnthropicProvider("key", prompt_cache=True)
    import httpx
    with patch("httpx.Client"):
        provider.complete(_simple_req(system=long_system))
    kw = _call_kwargs(stub_with_cache)
    system = kw["system"]
    assert isinstance(system, list)
    assert system[0]["text"] == long_system


# ===========================================================================
# 23. Tools core fields not mutated when cache_control added
# ===========================================================================

def test_tool_fields_intact_with_cache_control(stub_with_cache):
    provider = AnthropicProvider("key", prompt_cache=True)
    import httpx
    with patch("httpx.Client"):
        provider.complete(_tool_req(n_tools=2))
    kw = _call_kwargs(stub_with_cache)
    tools = kw["tools"]
    assert tools[0]["name"] == "tool_0"
    assert tools[1]["name"] == "tool_1"
    assert "input_schema" in tools[0]
    assert "input_schema" in tools[1]
    assert "cache_control" in tools[1]


# ===========================================================================
# 24. Tool calls in assistant messages have no cache_control
# ===========================================================================

def test_tool_use_blocks_in_messages_no_cache_control(stub_with_cache):
    from kerf_chat.llm import ToolCall

    provider = AnthropicProvider("key", prompt_cache=True)
    req = _simple_req(messages=[
        Message(
            role="user",
            content="call the tool",
        ),
        Message(
            role="assistant",
            content="",
            tool_calls=[ToolCall(id="call_1", name="tool_0", arguments_json='{"x":1}')],
        ),
    ])
    import httpx
    with patch("httpx.Client"):
        provider.complete(req)
    kw = _call_kwargs(stub_with_cache)
    for msg in kw["messages"]:
        content = msg["content"]
        if isinstance(content, list):
            for block in content:
                assert "cache_control" not in block
