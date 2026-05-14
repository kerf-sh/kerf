"""
Tests for the JSON-RPC client — asserts envelope shape, auth header,
error mapping, and namespace wrappers.

Uses respx to mock httpx at the transport level so no real network traffic.
"""

import pytest
import respx
import httpx

import kerf
from kerf.client import Kerf, KerfError


BASE = "https://kerf.app"
TOKEN = "kerf_sk_testtoken123"


@respx.mock
def test_invoke_sends_correct_jsonrpc_envelope():
    route = respx.post(f"{BASE}/v1/rpc").mock(
        return_value=httpx.Response(200, json={"jsonrpc": "2.0", "result": [], "id": "1"})
    )
    k = kerf.connect(TOKEN, BASE)
    result = k.invoke("files.list", {"project_id": "proj-1"})

    assert route.called
    request = route.calls[0].request
    body = httpx.Request("POST", BASE, content=request.content).read()

    import json
    payload = json.loads(body)
    assert payload["jsonrpc"] == "2.0"
    assert payload["method"] == "files.list"
    assert payload["params"] == {"project_id": "proj-1"}
    assert "id" in payload
    assert result == []


@respx.mock
def test_invoke_sets_bearer_auth_header():
    respx.post(f"{BASE}/v1/rpc").mock(
        return_value=httpx.Response(200, json={"jsonrpc": "2.0", "result": {}, "id": "1"})
    )
    k = kerf.connect(TOKEN, BASE)
    k.invoke("files.read", {"project_id": "p", "file_id": "f"})

    req = respx.calls[0].request
    assert req.headers["authorization"] == f"Bearer {TOKEN}"


@respx.mock
def test_invoke_raises_kerf_error_on_jsonrpc_error():
    respx.post(f"{BASE}/v1/rpc").mock(
        return_value=httpx.Response(200, json={
            "jsonrpc": "2.0",
            "error": {"code": -32600, "message": "project not found"},
            "id": "1",
        })
    )
    k = kerf.connect(TOKEN, BASE)
    with pytest.raises(KerfError) as exc_info:
        k.invoke("files.list", {"project_id": "missing"})
    assert exc_info.value.code == -32600
    assert "project not found" in str(exc_info.value)


@respx.mock
def test_files_list_namespace_wrapper():
    respx.post(f"{BASE}/v1/rpc").mock(
        return_value=httpx.Response(200, json={"jsonrpc": "2.0", "result": [{"id": "f1", "name": "part.jscad"}], "id": "1"})
    )
    k = kerf.connect(TOKEN, BASE)
    files = k.files.list("proj-1")
    assert files[0]["name"] == "part.jscad"

    import json
    payload = json.loads(respx.calls[0].request.content)
    assert payload["method"] == "files.list"
    assert payload["params"]["project_id"] == "proj-1"


@respx.mock
def test_from_env_reads_env_vars(monkeypatch):
    monkeypatch.setenv("KERF_API_TOKEN", "kerf_sk_envtoken")
    monkeypatch.setenv("KERF_API_URL", BASE)
    respx.post(f"{BASE}/v1/rpc").mock(
        return_value=httpx.Response(200, json={"jsonrpc": "2.0", "result": [], "id": "1"})
    )
    k = kerf.from_env()
    k.files.list("p")
    req = respx.calls[0].request
    assert req.headers["authorization"] == "Bearer kerf_sk_envtoken"


def test_from_env_raises_when_token_missing(monkeypatch):
    monkeypatch.delenv("KERF_API_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="KERF_API_TOKEN"):
        kerf.from_env()


@respx.mock
def test_context_manager_closes_client():
    respx.post(f"{BASE}/v1/rpc").mock(
        return_value=httpx.Response(200, json={"jsonrpc": "2.0", "result": [], "id": "1"})
    )
    with kerf.connect(TOKEN, BASE) as k:
        k.files.list("p")
