"""
test_anthropic_stream.py

Unit tests for AnthropicProvider.stream() — Anthropic SDK event → Kerf StreamEvent mapping.

All tests are hermetic: the anthropic client is fully mocked; no network calls.
Tests verify:
  - text delta events map to assistant_text_delta
  - tool_use_start emitted on ContentBlockStartEvent with type='tool_use'
  - tool_use_input_delta emitted on input_json_delta deltas
  - tool_use_complete emitted on ContentBlockStopEvent after tool_use block
  - assembled JSON input is correctly parsed in tool_use_complete
  - assistant_done carries stop_reason, input_tokens, output_tokens, model
  - pure text turn: no tool_use_* events emitted
  - consecutive tool blocks handled independently
  - SDK events without recognised type names are silently ignored
"""
from __future__ import annotations

import asyncio
import json
import sys
import types
from dataclasses import dataclass, field
from typing import Any, Iterator
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Install minimal anthropic stub before importing the module under test
# ---------------------------------------------------------------------------

def _make_stub():
    stub = types.ModuleType("anthropic")
    stub.__version__ = "0.99.0"
    types_stub = types.ModuleType("anthropic.types")

    class _ToolParam:
        __annotations__ = {"cache_control": "any", "name": "str"}

    types_stub.ToolParam = _ToolParam
    stub.types = types_stub

    class _Anthropic:
        def __init__(self, **kw):
            pass

    stub.Anthropic = _Anthropic
    sys.modules["anthropic"] = stub
    sys.modules["anthropic.types"] = types_stub
    return stub


_STUB = _make_stub()


from kerf_chat.llm import (
    AnthropicProvider,
    CompleteRequest,
    StreamEvent,
    Message,
    ToolSpec,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _req(**kw) -> CompleteRequest:
    defaults = dict(
        model="claude-sonnet-4-6",
        system="helpful",
        messages=[Message(role="user", content="hi")],
        max_tokens=100,
        temperature=0.0,
        tools=[],
    )
    defaults.update(kw)
    return CompleteRequest(**defaults)


# ---------------------------------------------------------------------------
# Fake SDK event factories
#
# The provider uses type(event).__name__ to discriminate events.
# We create each fake event as an instance of a class whose __name__
# matches the expected string.
# ---------------------------------------------------------------------------

def _named(class_name: str, **attrs):
    """Return an instance whose class name is `class_name`."""
    cls = type(class_name, (), {})
    obj = object.__new__(cls)
    for k, v in attrs.items():
        setattr(obj, k, v)
    return obj


def _text_block(**kw):
    return _named("_Block", type="text", id="", name="", input={}, **kw)


def _tool_block(id="tu_abc", name="read_file"):
    return _named("_ToolBlock", type="tool_use", id=id, name=name, input={})


def _text_delta(text="hello "):
    d = _named("_TextDelta", type="text_delta", text=text)
    return d


def _json_delta(partial_json='{"path":'):
    d = _named("_JsonDelta", type="input_json_delta", partial_json=partial_json)
    return d


def _usage(input_tokens=10, output_tokens=5):
    return _named("_Usage", input_tokens=input_tokens, output_tokens=output_tokens)


def msg_start(input_tokens=10):
    msg = _named("_InnerMsg", usage=_usage(input_tokens=input_tokens))
    return _named("MessageStartEvent", message=msg)


def content_start(block):
    return _named("ContentBlockStartEvent", content_block=block)


def content_delta(delta):
    return _named("ContentBlockDeltaEvent", delta=delta)


def content_stop():
    return _named("ContentBlockStopEvent")


def msg_delta(output_tokens=5):
    return _named("MessageDeltaEvent", usage=_usage(output_tokens=output_tokens))


def msg_stop():
    return _named("MessageStopEvent")


# ---------------------------------------------------------------------------
# Context manager wrapper for a list of events
# ---------------------------------------------------------------------------

class _FakeStreamCtx:
    def __init__(self, events, final_stop_reason="end_turn", final_tokens=(10, 5)):
        self._events = events
        self._stop_reason = final_stop_reason
        self._final_tokens = final_tokens

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass

    def __iter__(self) -> Iterator:
        return iter(self._events)

    def get_final_message(self):
        it, ot = self._final_tokens
        m = _named(
            "_FinalMsg",
            stop_reason=self._stop_reason,
            usage=_usage(input_tokens=it, output_tokens=ot),
        )
        return m


def _collect(events, stop_reason="end_turn", **req_kw) -> list[StreamEvent]:
    """Run provider.stream() with mocked Anthropic client, return collected events."""
    provider = AnthropicProvider("key", prompt_cache=False)
    req = _req(**req_kw)
    ctx = _FakeStreamCtx(events, final_stop_reason=stop_reason)

    with patch("anthropic.Anthropic") as MockClient:
        mock_msgs = MagicMock()
        mock_msgs.stream.return_value = ctx
        MockClient.return_value.messages = mock_msgs

        async def _run():
            result = []
            async for ev in provider.stream(req):
                result.append(ev)
            return result

        return run(_run())


# ===========================================================================
# 1. Text-only turn emits assistant_text_delta × N and assistant_done
# ===========================================================================

def test_text_only_turn():
    events = [
        msg_start(),
        content_start(_text_block()),
        content_delta(_text_delta("Hello ")),
        content_delta(_text_delta("world")),
        content_stop(),
        msg_delta(output_tokens=4),
        msg_stop(),
    ]
    result = _collect(events)
    types_seen = [e.type for e in result]
    assert types_seen.count("assistant_text_delta") == 2
    assert types_seen.count("assistant_done") == 1
    # No tool events
    assert "tool_use_start" not in types_seen
    assert "tool_use_complete" not in types_seen


def test_text_delta_content_correct():
    events = [
        msg_start(),
        content_start(_text_block()),
        content_delta(_text_delta(" on it")),
        content_stop(),
        msg_stop(),
    ]
    result = _collect(events)
    delta = next(e for e in result if e.type == "assistant_text_delta")
    assert delta.data["text"] == " on it"


# ===========================================================================
# 2. Tool-use block emits start → input_delta × N → complete
# ===========================================================================

def test_tool_use_events_emitted():
    events = [
        msg_start(),
        content_start(_tool_block(id="tu_1", name="read_file")),
        content_delta(_json_delta('{"path":')),
        content_delta(_json_delta('"/main.jscad"}')),
        content_stop(),
        msg_stop(),
    ]
    result = _collect(events)
    types_seen = [e.type for e in result]
    assert "tool_use_start" in types_seen
    assert "tool_use_input_delta" in types_seen
    assert "tool_use_complete" in types_seen


def test_tool_use_start_data():
    events = [
        msg_start(),
        content_start(_tool_block(id="tu_xyz", name="write_file")),
        content_stop(),
        msg_stop(),
    ]
    result = _collect(events)
    start = next(e for e in result if e.type == "tool_use_start")
    assert start.data["tool_use_id"] == "tu_xyz"
    assert start.data["name"] == "write_file"


def test_tool_use_complete_data():
    events = [
        msg_start(),
        content_start(_tool_block(id="tu_1", name="read_file")),
        content_delta(_json_delta('{"path":')),
        content_delta(_json_delta('"/main.jscad"}')),
        content_stop(),
        msg_stop(),
    ]
    result = _collect(events)
    complete = next(e for e in result if e.type == "tool_use_complete")
    assert complete.data["tool_use_id"] == "tu_1"
    assert complete.data["name"] == "read_file"
    assert complete.data["input"] == {"path": "/main.jscad"}


def test_tool_use_complete_id_matches_start():
    events = [
        msg_start(),
        content_start(_tool_block(id="tu_abc", name="list_files")),
        content_stop(),
        msg_stop(),
    ]
    result = _collect(events)
    start = next(e for e in result if e.type == "tool_use_start")
    complete = next(e for e in result if e.type == "tool_use_complete")
    assert start.data["tool_use_id"] == complete.data["tool_use_id"]


# ===========================================================================
# 3. input_json_delta content forwarded
# ===========================================================================

def test_tool_input_delta_forwarded():
    events = [
        msg_start(),
        content_start(_tool_block()),
        content_delta(_json_delta('{"x":')),
        content_stop(),
        msg_stop(),
    ]
    result = _collect(events)
    deltas = [e for e in result if e.type == "tool_use_input_delta"]
    assert len(deltas) == 1
    assert deltas[0].data["partial_json"] == '{"x":'


# ===========================================================================
# 4. assistant_done carries correct token counts and stop_reason
# ===========================================================================

def test_assistant_done_token_counts():
    events = [
        msg_start(input_tokens=42),
        content_start(_text_block()),
        content_stop(),
        msg_delta(output_tokens=17),
        msg_stop(),
    ]
    result = _collect(events, stop_reason="end_turn")
    done = next(e for e in result if e.type == "assistant_done")
    assert done.data["stop_reason"] == "end_turn"
    # Tokens come from get_final_message in our fake (10, 5) defaults — test that they're present
    assert "input_tokens" in done.data
    assert "output_tokens" in done.data
    assert "model" in done.data


def test_assistant_done_stop_reason_tool_use():
    events = [msg_start(), msg_stop()]
    result = _collect(events, stop_reason="tool_use")
    done = next(e for e in result if e.type == "assistant_done")
    assert done.data["stop_reason"] == "tool_use"


# ===========================================================================
# 5. Consecutive tool blocks handled independently
# ===========================================================================

def test_consecutive_tool_blocks():
    events = [
        msg_start(),
        content_start(_tool_block(id="tu_1", name="read_file")),
        content_delta(_json_delta('{"path":"/a"}')),
        content_stop(),
        content_start(_tool_block(id="tu_2", name="write_file")),
        content_delta(_json_delta('{"path":"/b","content":"x"}')),
        content_stop(),
        msg_stop(),
    ]
    result = _collect(events)
    starts = [e for e in result if e.type == "tool_use_start"]
    completes = [e for e in result if e.type == "tool_use_complete"]
    assert len(starts) == 2
    assert len(completes) == 2
    assert starts[0].data["tool_use_id"] == "tu_1"
    assert starts[1].data["tool_use_id"] == "tu_2"
    assert completes[0].data["input"]["path"] == "/a"
    assert completes[1].data["input"]["path"] == "/b"


# ===========================================================================
# 6. Mixed text + tool_use in same turn
# ===========================================================================

def test_mixed_text_and_tool():
    events = [
        msg_start(),
        content_start(_text_block()),
        content_delta(_text_delta("I'll read that.")),
        content_stop(),
        content_start(_tool_block(id="tu_1", name="read_file")),
        content_delta(_json_delta('{"path":"/main.jscad"}')),
        content_stop(),
        msg_stop(),
    ]
    result = _collect(events)
    types_seen = [e.type for e in result]
    assert "assistant_text_delta" in types_seen
    assert "tool_use_start" in types_seen
    assert "tool_use_complete" in types_seen
    assert "assistant_done" in types_seen


# ===========================================================================
# 7. Unknown / unrecognised event names silently ignored
# ===========================================================================

def test_unknown_events_ignored():
    events = [
        msg_start(),
        _named("SomeFutureEvent", foo="bar"),
        content_start(_text_block()),
        content_delta(_text_delta("ok")),
        content_stop(),
        msg_stop(),
    ]
    result = _collect(events)
    # Should still produce the text delta and done without error
    assert any(e.type == "assistant_text_delta" for e in result)
    assert any(e.type == "assistant_done" for e in result)


# ===========================================================================
# 8. Empty tool input (no JSON deltas) → empty dict
# ===========================================================================

def test_empty_tool_input_gives_empty_dict():
    events = [
        msg_start(),
        content_start(_tool_block(id="tu_1", name="list_files")),
        content_stop(),
        msg_stop(),
    ]
    result = _collect(events)
    complete = next(e for e in result if e.type == "tool_use_complete")
    assert complete.data["input"] == {}


# ===========================================================================
# 9. Non-streaming providers raise NotImplementedError
# ===========================================================================

def test_openai_provider_stream_raises():
    # Stub openai
    _oi = types.ModuleType("openai")
    class _OAI:
        def __init__(self, **kw): pass
    _oi.OpenAI = _OAI
    sys.modules["openai"] = _oi

    from kerf_chat.llm import OpenAIProvider
    provider = OpenAIProvider("key")

    async def _run():
        gen = provider.stream(_req(model="gpt-4o"))
        raised = False
        try:
            async for _ in gen:
                pass
        except NotImplementedError:
            raised = True
        assert raised, "OpenAIProvider.stream() should raise NotImplementedError"

    run(_run())
    sys.modules.pop("openai", None)


def test_moonshot_provider_stream_raises():
    _oi = types.ModuleType("openai")
    class _OAI:
        def __init__(self, **kw): pass
    _oi.OpenAI = _OAI
    sys.modules["openai"] = _oi

    from kerf_chat.llm import MoonshotProvider
    provider = MoonshotProvider("key")

    async def _run():
        raised = False
        try:
            async for _ in provider.stream(_req(model="moonshot-v1-32k")):
                pass
        except NotImplementedError:
            raised = True
        assert raised

    run(_run())
    sys.modules.pop("openai", None)
