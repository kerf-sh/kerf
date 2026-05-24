#!/usr/bin/env python3
"""End-to-end chat probe against a live Kerf deployment.

Self-contained: registers a fresh disposable user, creates a project,
drives the SSE `/messages/stream` endpoint with a real prompt, logs every
event that comes back, and deletes everything on the way out.

Usage:
    KERF_BASE_URL=https://kerf-dev.koyeb.app \\
    python scripts/e2e_chat_probe.py

Optional env vars:
    KERF_MODEL    — model id to send (else server default)
    KERF_PROMPT   — chat prompt (default: "make me a box with a lid")
    KERF_TIMEOUT  — read timeout seconds (default 180)
    KERF_VERBOSE  — "1" to dump raw events

The script:
  1. POST /auth/register  → fresh user, fresh access token.
  2. POST /api/projects   → fresh project (gets auto-git-init).
  3. POST /api/projects/{pid}/threads → fresh thread.
  4. POST /messages/stream → parse every SSE frame; log + classify.
  5. GET /files/main.jscad → did the assistant actually write the box?
  6. DELETE /api/projects/{pid}?confirm=DELETE → cleanup.
  7. DELETE /api/me?confirm=DELETE → delete the disposable user.

Exit codes:
  0  stream looked healthy
  1  fatal error before stream (auth, project create, …)
  2  server emitted `event: error` mid-stream
  3  stream connected but emitted ZERO events
  4  stream completed with no text AND no tool calls (Anthropic empty)
  5  tools called but no final text (loop never resolved)

The summary ends with a one-line `VERDICT:` so the script is greppable
in CI logs.
"""
from __future__ import annotations

import json
import os
import secrets
import sys
import time
from typing import Iterator

import httpx


BASE_URL = os.environ.get("KERF_BASE_URL", "https://kerf-dev.koyeb.app").rstrip("/")
MODEL = os.environ.get("KERF_MODEL", "").strip()
PROMPT = os.environ.get("KERF_PROMPT", "make me a box with a lid")
TIMEOUT = float(os.environ.get("KERF_TIMEOUT", "180"))
VERBOSE = os.environ.get("KERF_VERBOSE", "").strip() in ("1", "true", "yes")

# When KERF_MODELS is set (comma-separated), the script loops through each
# model. Otherwise it uses KERF_MODEL (or the server default).
MODELS = [s.strip() for s in os.environ.get("KERF_MODELS", "").split(",") if s.strip()]


def _h(token: str, **extras) -> dict:
    h = {"authorization": f"Bearer {token}", "content-type": "application/json"}
    h.update(extras)
    return h


# ── Seeded test user ────────────────────────────────────────────────────────


def _register_test_user() -> tuple[str, str, str]:
    """Register a disposable user. Returns (email, password, access_token)."""
    suffix = secrets.token_hex(6)
    email = f"e2e-probe-{suffix}@example.test"
    password = secrets.token_urlsafe(24)
    name = f"E2E Probe {suffix}"
    r = httpx.post(
        f"{BASE_URL}/auth/register",
        json={"email": email, "password": password, "name": name},
        timeout=30.0,
    )
    if r.status_code >= 300:
        raise RuntimeError(f"register {r.status_code}: {r.text[:300]}")
    token = r.json()["access_token"]
    print(f"✓ user seeded:  {email}")
    return email, password, token


def _delete_self(token: str) -> None:
    """Best-effort: delete the disposable user account."""
    try:
        r = httpx.delete(
            f"{BASE_URL}/api/me?confirm=DELETE",
            headers=_h(token),
            timeout=30.0,
        )
        if r.status_code < 300:
            print("✓ user deleted")
        else:
            print(f"(cleanup) delete user {r.status_code}: {r.text[:120]}")
    except Exception as e:
        print(f"(cleanup) delete user failed: {e}")


# ── Project + thread ────────────────────────────────────────────────────────


def _create_project(token: str) -> str:
    name = f"e2e-probe-{int(time.time())}"
    r = httpx.post(
        f"{BASE_URL}/api/projects",
        json={"name": name, "description": "automated E2E chat probe"},
        headers=_h(token),
        timeout=30.0,
    )
    if r.status_code >= 300:
        raise RuntimeError(f"create_project {r.status_code}: {r.text[:300]}")
    pid = r.json()["id"]
    print(f"✓ project:      {pid}  ({name})")
    return pid


def _create_thread(token: str, pid: str, model: str = "") -> str:
    body: dict = {"title": "e2e"}
    if model:
        body["model"] = model
    r = httpx.post(
        f"{BASE_URL}/api/projects/{pid}/threads",
        json=body,
        headers=_h(token),
        timeout=30.0,
    )
    if r.status_code >= 300:
        raise RuntimeError(f"create_thread {r.status_code}: {r.text[:300]}")
    tid = r.json()["id"]
    print(f"✓ thread:       {tid}")
    return tid


def _delete_project(token: str, pid: str) -> None:
    try:
        httpx.delete(
            f"{BASE_URL}/api/projects/{pid}?confirm=DELETE",
            headers=_h(token),
            timeout=30.0,
        )
        print(f"✓ project deleted: {pid}")
    except Exception as e:
        print(f"(cleanup) delete project: {e}")


# ── Stream ──────────────────────────────────────────────────────────────────


def _stream(token: str, pid: str, tid: str, prompt: str, model: str = "") -> Iterator[dict]:
    body: dict = {"content": prompt}
    if model:
        body["model"] = model
    url = f"{BASE_URL}/api/projects/{pid}/threads/{tid}/messages/stream"
    with httpx.Client(timeout=httpx.Timeout(TIMEOUT, read=TIMEOUT)) as c:
        with c.stream(
            "POST", url,
            json=body,
            headers=_h(token, accept="text/event-stream"),
        ) as r:
            if r.status_code >= 300:
                body_text = r.read().decode("utf-8", errors="replace")
                raise RuntimeError(f"stream HTTP {r.status_code}: {body_text[:400]}")
            buf = ""
            for chunk in r.iter_text():
                buf += chunk
                while "\n\n" in buf:
                    frame, buf = buf.split("\n\n", 1)
                    event = "message"
                    data_lines: list[str] = []
                    for line in frame.split("\n"):
                        if line.startswith(":"):
                            continue
                        elif line.startswith("event:"):
                            event = line[6:].strip()
                        elif line.startswith("data:"):
                            data_lines.append(line[5:].strip())
                    if not data_lines:
                        continue
                    raw = "\n".join(data_lines)
                    try:
                        data = json.loads(raw)
                    except json.JSONDecodeError:
                        data = raw
                    yield {"event": event, "data": data}


def _fetch_file(token: str, pid: str, name: str = "main.jscad") -> tuple[bool, str]:
    r = httpx.get(
        f"{BASE_URL}/api/projects/{pid}/files",
        headers=_h(token),
        timeout=30.0,
    )
    if r.status_code >= 300:
        return False, f"list files {r.status_code}"
    files = r.json()
    target = next((f for f in files if f.get("name") == name), None)
    if not target:
        names = [f["name"] for f in files]
        return False, f"file {name!r} not found  (project has: {names})"
    fid = target["id"]
    r = httpx.get(
        f"{BASE_URL}/api/projects/{pid}/files/{fid}",
        headers=_h(token),
        timeout=30.0,
    )
    if r.status_code >= 300:
        return False, f"get file {r.status_code}"
    return True, r.json().get("content", "")


# ── Main ────────────────────────────────────────────────────────────────────


def run_one(model_override: str = "") -> int:
    """Run one probe. model_override (if non-empty) takes precedence over $KERF_MODEL."""
    model = model_override or MODEL
    print(f"━━━ E2E chat probe ━━━")
    print(f"  base    : {BASE_URL}")
    print(f"  model   : {model or '(server default)'}")
    print(f"  prompt  : {PROMPT}")
    print()

    email, _password, token = _register_test_user()
    pid: str = ""
    try:
        pid = _create_project(token)
        tid = _create_thread(token, pid, model=model)

        print()
        print(f"━━━ Streaming response ━━━")
        t0 = time.time()
        events: list[dict] = []
        text_chunks: list[str] = []
        tool_calls: list[dict] = []
        tool_results: list[dict] = []
        stop_reason = None
        error_event = None

        for ev in _stream(token, pid, tid, PROMPT, model=model):
            elapsed = time.time() - t0
            etype = ev["event"]
            data = ev["data"]
            events.append(ev)

            if VERBOSE:
                print(f"  [{elapsed:5.1f}s] RAW {etype}  {json.dumps(data)[:200]}")
                continue

            if etype == "assistant_text_delta":
                txt = data.get("text", "") if isinstance(data, dict) else ""
                text_chunks.append(txt)
                preview = txt.replace("\n", " ")[:50]
                print(f"  [{elapsed:5.1f}s] text_delta   {preview!r}")
            elif etype == "tool_use_start":
                if isinstance(data, dict):
                    print(f"  [{elapsed:5.1f}s] tool_start   {data.get('name')}  ({data.get('tool_use_id')})")
                    tool_calls.append(data)
            elif etype == "tool_use_complete":
                if isinstance(data, dict):
                    inp = json.dumps(data.get("input", {}))[:100]
                    print(f"  [{elapsed:5.1f}s] tool_input   {data.get('name')}  input={inp}")
            elif etype == "tool_executing":
                if isinstance(data, dict):
                    print(f"  [{elapsed:5.1f}s] tool_running {data.get('name', '')}")
            elif etype == "tool_result":
                if isinstance(data, dict):
                    is_err = data.get("is_error")
                    preview = (data.get("content_preview") or "")[:120]
                    flag = " ⚠ ERROR" if is_err else ""
                    print(f"  [{elapsed:5.1f}s] tool_result{flag}  preview={preview!r}")
                    tool_results.append(data)
            elif etype == "assistant_done":
                if isinstance(data, dict):
                    stop_reason = data.get("stop_reason")
                    print(f"  [{elapsed:5.1f}s] assistant_done  stop={stop_reason}  in={data.get('input_tokens')} out={data.get('output_tokens')}")
            elif etype == "error":
                error_event = data
                print(f"  [{elapsed:5.1f}s] ERROR  {data}")
            elif etype == "user_message":
                pass
            else:
                print(f"  [{elapsed:5.1f}s] {etype}  {str(data)[:80]}")

        duration = time.time() - t0
        text_total = "".join(text_chunks)
        print()
        print(f"━━━ Summary ━━━")
        print(f"  duration       : {duration:.1f}s")
        print(f"  events         : {len(events)}")
        print(f"  text chars     : {len(text_total)}")
        print(f"  tool calls     : {len(tool_calls)}  {[c.get('name') for c in tool_calls]}")
        print(f"  tool errors    : {sum(1 for t in tool_results if t.get('is_error'))} / {len(tool_results)}")
        print(f"  stop_reason    : {stop_reason}")
        print(f"  error event    : {error_event}")

        ok, content_or_err = _fetch_file(token, pid)
        if ok:
            sniff = content_or_err.lower()
            mutated = bool(content_or_err) and ("cuboid" in sniff or "box" in sniff or "subtract" in sniff)
            print(f"  main.jscad     : {len(content_or_err)} chars  looks_box_shaped={mutated}")
        else:
            print(f"  main.jscad     : {content_or_err}")

        print()
        if error_event:
            print(f"VERDICT: server reported an error mid-stream. fix this first: {error_event}")
            return 2
        elif len(events) == 0:
            print("VERDICT: ZERO events from server. stream connected but emitted nothing.")
            return 3
        elif len(tool_calls) == 0 and len(text_total) == 0:
            print("VERDICT: empty response. stream done with no text and no tool calls (Anthropic returned nothing).")
            return 4
        elif len(tool_calls) > 0 and len(text_total) == 0 and stop_reason in (None, "end_turn"):
            print("VERDICT: tools called but no final text. agent loop did not continue past tool_use.")
            return 5
        else:
            print("VERDICT: stream healthy.")
            return 0
    finally:
        if pid:
            _delete_project(token, pid)
        _delete_self(token)


def run_many(models: list[str]) -> int:
    """Run the probe once per model; exit nonzero if ANY model fails.

    Each model gets its own seeded user + project so the runs are
    fully isolated. Summary table at the end.
    """
    results: list[tuple[str, int]] = []
    for m in models:
        print()
        print("=" * 72)
        try:
            code = run_one(model_override=m)
        except KeyboardInterrupt:
            raise
        except Exception as e:
            print(f"FATAL during {m}: {type(e).__name__}: {e}")
            code = 1
        results.append((m, code))

    print()
    print("=" * 72)
    print("Multi-model summary:")
    worst = 0
    for m, code in results:
        flag = "✓" if code == 0 else "✗"
        print(f"  {flag} {m:40s} exit={code}")
        worst = max(worst, code)
    return worst


if __name__ == "__main__":
    try:
        if MODELS:
            sys.exit(run_many(MODELS))
        else:
            sys.exit(run_one())
    except KeyboardInterrupt:
        print("\nINTERRUPTED")
        sys.exit(130)
    except Exception as e:
        print(f"\nFATAL: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
