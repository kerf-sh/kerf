#!/usr/bin/env python3
"""
Kerf API Integration Test Reference
===================================

This script demonstrates how to interact with the Kerf API using raw HTTP requests.
It shows the exact HTTP shapes for authentication, file operations, and error handling.

Usage:
    KERF_URL=https://app.kerf.dev python3 examples/kerf_sdk_example.py
    KERF_URL=http://localhost:8080 python3 examples/kerf_sdk_example.py

Requirements: requests (pip install requests)
"""

import json
import os
import sys
import base64
from typing import Any, Optional

import requests

# Configuration — set KERF_URL env var to target different servers
BASE_URL = os.environ.get("KERF_URL", "http://localhost:8080")

# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def get_headers(token: str) -> dict:
    """Build standard auth headers."""
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def rpc_call(token: str, method: str, params: dict, req_id: Any = 1) -> dict:
    """
    Make a JSON-RPC 2.0 call to /v1/rpc.

    Args:
        token: Bearer JWT token
        method: RPC method name (e.g., "files.list")
        params: Method parameters (must include project_id)
        req_id: Request identifier (for response matching)

    Returns:
        Full JSON-RPC response dict. Caller should check for "result" or "error" key.

    Raises:
        requests.HTTPError: On network/HTTP-level errors (4xx/5xx responses).
    """
    payload = {
        "jsonrpc": "2.0",
        "method": method,
        "params": params,
        "id": req_id,
    }
    resp = requests.post(
        f"{BASE_URL}/v1/rpc",
        headers=get_headers(token),
        json=payload,
    )
    resp.raise_for_status()
    return resp.json()


def handle_rpc_response(data: dict) -> Any:
    """
    Unpack a JSON-RPC response.

    - If "result" is present, return it.
    - If "error" is present, raise an exception with the error code and message.
    - Otherwise, raise a generic error.
    """
    if "result" in data:
        return data["result"]
    if "error" in data:
        code = data["error"].get("code", -32603)
        message = data["error"].get("message", "unknown error")
        raise RuntimeError(f"RPC error {code}: {message}")
    raise RuntimeError(f"Malformed RPC response: {data}")


# ----------------------------------------------------------------------
# Authentication
# ----------------------------------------------------------------------


def get_token(email: str, password: str) -> str:
    """
    Authenticate with email/password and return the access token.

    API: POST /auth/login
    Body: {"email": "...", "password": "..."}
    Response: {"access_token": "...", "refresh_token": "...", "user": {...}, ...}
    """
    resp = requests.post(
        f"{BASE_URL}/auth/login",
        json={"email": email, "password": password},
    )
    resp.raise_for_status()
    data = resp.json()
    return data["access_token"]


def create_api_token(token: str, name: str) -> str:
    """
    Create a long-lived API token for machine-to-machine auth.

    API: POST /api/api-tokens
    Body: {"name": "my-token"}
    Response: {"id": "...", "name": "...", "token": "...", "scopes": [...]}

    Note: The returned "token" field is only shown once — store it securely.
    """
    resp = requests.post(
        f"{BASE_URL}/api/api-tokens",
        headers=get_headers(token),
        json={"name": name},
    )
    resp.raise_for_status()
    data = resp.json()
    return data["token"]


# ----------------------------------------------------------------------
# File Operations
# ----------------------------------------------------------------------


def list_files(token: str, project_id: str) -> list:
    """
    List all files in a project.

    RPC: files.list
    Params: {"project_id": "..."}
    Result: [{"id": "...", "name": "...", "kind": "...", ...}, ...]
    """
    data = rpc_call(token, "files.list", {"project_id": project_id})
    return handle_rpc_response(data)


def read_file(token: str, project_id: str, file_id: str) -> dict:
    """
    Read a file's content and metadata.

    RPC: files.read
    Params: {"project_id": "...", "file_id": "..."}
    Result: {"id": "...", "name": "...", "content": "...", "kind": "...", ...}
    """
    data = rpc_call(token, "files.read", {"project_id": project_id, "file_id": file_id})
    return handle_rpc_response(data)


def write_file(token: str, project_id: str, file_id: str, content: str) -> dict:
    """
    Overwrite a file's content.

    RPC: files.write
    Params: {"project_id": "...", "file_id": "...", "content": "..."}
    Result: {"ok": true}
    """
    data = rpc_call(
        token, "files.write", {"project_id": project_id, "file_id": file_id, "content": content}
    )
    return handle_rpc_response(data)


def create_file(token: str, project_id: str, name: str, kind: str = "source", parent_id: Optional[str] = None) -> dict:
    """
    Create a new file.

    RPC: files.create
    Params: {"project_id": "...", "name": "...", "kind": "...", "parent_id": "..."}
    Result: {"id": "...", "name": "...", "kind": "...", ...}
    """
    params = {"project_id": project_id, "name": name, "kind": kind}
    if parent_id:
        params["parent_id"] = parent_id
    data = rpc_call(token, "files.create", params)
    return handle_rpc_response(data)


def delete_file(token: str, project_id: str, file_id: str) -> dict:
    """
    Delete a file.

    RPC: files.delete
    Params: {"project_id": "...", "file_id": "..."}
    Result: {"ok": true}
    """
    data = rpc_call(token, "files.delete", {"project_id": project_id, "file_id": file_id})
    return handle_rpc_response(data)


def search_files(token: str, project_id: str, query: str) -> list:
    """
    Search file contents within a project.

    RPC: files.search
    Params: {"project_id": "...", "query": "..."}
    Result: [{"file_id": "...", "snippet": "...", "line_number": N, ...}, ...]
    """
    data = rpc_call(token, "files.search", {"project_id": project_id, "query": query})
    return handle_rpc_response(data)


# ----------------------------------------------------------------------
# Documentation Search
# ----------------------------------------------------------------------


def search_docs(token: str, query: str) -> list:
    """
    Search Kerf documentation.

    RPC: docs.search
    Params: {"query": "..."}
    Result: [{"title": "...", "snippet": "...", "url": "..."}, ...]
    """
    data = rpc_call(token, "docs.search", {"query": query})
    return handle_rpc_response(data)


# ----------------------------------------------------------------------
# Error Handling Examples
# ----------------------------------------------------------------------


def demonstrate_errors(token: str, project_id: str):
    """
    Show how to handle various error responses.
    """
    print("\n--- Error Handling Demo ---")

    # 1. Method not found — RPC error with code -32601
    try:
        rpc_call(token, "nonexistent.method", {"project_id": project_id})
    except requests.HTTPError as e:
        # HTTP-level error (4xx/5xx) — shouldn't happen for RPC errors which return 200
        print(f"HTTP error (unexpected): {e}")
    else:
        pass  # Should not reach here

    # 2. Missing required param — RPC error with code -32602
    try:
        rpc_call(token, "files.read", {})  # missing project_id and file_id
    except RuntimeError as e:
        print(f"Caught expected error: {e}")

    # 3. Invalid credentials — HTTP 401
    try:
        bad_token = "eyJinvalid.token.here"
        rpc_call(bad_token, "files.list", {"project_id": project_id})
    except requests.HTTPError as e:
        print(f"Caught HTTP 401 (expected): {e}")

    # 4. Access denied to project — RPC error with code -32600 in result
    try:
        # Using a token that doesn't have access to this project
        rpc_call(token, "files.list", {"project_id": "00000000-0000-0000-0000-000000000000"})
    except RuntimeError as e:
        print(f"Caught access-denied error (expected): {e}")


# ----------------------------------------------------------------------
# Demo Flow
# ----------------------------------------------------------------------


def run_demo():
    """
    Run a complete demo flow with graceful error handling.

    This function is designed to work against both local and cloud servers,
    catching errors gracefully so the script can serve as a reference without
    requiring a fully configured live environment.
    """
    print(f"Targeting Kerf at: {BASE_URL}\n")

    # ------------------------------------------------------------------
    # Step 1: Authentication
    # ------------------------------------------------------------------
    print("Step 1: Authenticate")
    print("  POST /auth/login  {\"email\": \"...\", \"password\": \"...\"}")

    email = os.environ.get("KERF_EMAIL", "demo@kerf.dev")
    password = os.environ.get("KERF_PASSWORD", "demo-password")

    try:
        token = get_token(email, password)
        print(f"  Got token: {token[:20]}...")
    except requests.HTTPError as e:
        print(f"  Auth failed (expected in demo mode): {e}")
        print("  Set KERF_EMAIL and KERF_PASSWORD env vars to test with real credentials.")
        return

    # ------------------------------------------------------------------
    # Step 2: List Projects (REST, not RPC)
    # ------------------------------------------------------------------
    print("\nStep 2: List Projects")
    print("  GET /api/projects")

    try:
        resp = requests.get(f"{BASE_URL}/api/projects", headers=get_headers(token))
        resp.raise_for_status()
        projects = resp.json()
        print(f"  Found {len(projects)} project(s)")
        if projects:
            project_id = projects[0]["id"]
            print(f"  Using project: {project_id}")
        else:
            print("  No projects found — create one first")
            return
    except requests.HTTPError as e:
        print(f"  Could not list projects: {e}")
        return

    # ------------------------------------------------------------------
    # Step 3: List Files (RPC)
    # ------------------------------------------------------------------
    print("\nStep 3: List Files (RPC)")
    print('  POST /v1/rpc  {"method": "files.list", "params": {"project_id": "..."}}')

    try:
        files = list_files(token, project_id)
        print(f"  Found {len(files)} file(s)")
        for f in files[:3]:
            print(f"    - {f.get('name')} ({f.get('kind')})")
    except RuntimeError as e:
        print(f"  RPC error: {e}")
    except requests.HTTPError as e:
        print(f"  HTTP error: {e}")

    # ------------------------------------------------------------------
    # Step 4: Read a File (RPC)
    # ------------------------------------------------------------------
    if files:
        print("\nStep 4: Read a File (RPC)")
        print('  POST /v1/rpc  {"method": "files.read", "params": {"project_id": "...", "file_id": "..."}}')

        file_id = files[0].get("id")
        try:
            file_data = read_file(token, project_id, file_id)
            content_preview = file_data.get("content", "")[:100]
            print(f"  Content preview: {content_preview!r}")
        except RuntimeError as e:
            print(f"  RPC error: {e}")
        except requests.HTTPError as e:
            print(f"  HTTP error: {e}")

    # ------------------------------------------------------------------
    # Step 5: Create a File (RPC)
    # ------------------------------------------------------------------
    print("\nStep 5: Create a File (RPC)")
    print('  POST /v1/rpc  {"method": "files.create", "params": {"project_id": "...", "name": "test.txt"}}')

    try:
        new_file = create_file(token, project_id, name="test_file.txt", kind="text")
        print(f"  Created file: {new_file.get('id')} - {new_file.get('name')}")
    except RuntimeError as e:
        print(f"  RPC error (file may already exist): {e}")
    except requests.HTTPError as e:
        print(f"  HTTP error: {e}")

    # ------------------------------------------------------------------
    # Step 6: Write to File (RPC)
    # ------------------------------------------------------------------
    if files:
        print("\nStep 6: Write to File (RPC)")
        print('  POST /v1/rpc  {"method": "files.write", "params": {"project_id": "...", "file_id": "...", "content": "..."}}')

        file_id = files[0].get("id")
        try:
            result = write_file(token, project_id, file_id, content="Hello, Kerf!")
            print(f"  Write result: {result}")
        except RuntimeError as e:
            print(f"  RPC error: {e}")
        except requests.HTTPError as e:
            print(f"  HTTP error: {e}")

    # ------------------------------------------------------------------
    # Step 7: Search Docs (RPC)
    # ------------------------------------------------------------------
    print("\nStep 7: Search Documentation (RPC)")
    print('  POST /v1/rpc  {"method": "docs.search", "params": {"query": "assemblies"}}')

    try:
        results = search_docs(token, "assemblies")
        print(f"  Found {len(results)} doc(s)")
        for r in results[:3]:
            print(f"    - {r.get('title')}: {r.get('url')}")
    except RuntimeError as e:
        print(f"  RPC error: {e}")
    except requests.HTTPError as e:
        print(f"  HTTP error: {e}")

    # ------------------------------------------------------------------
    # Step 8: Error Handling Demo
    # ------------------------------------------------------------------
    demonstrate_errors(token, project_id)

    print("\n--- Demo Complete ---")
    print("\nTo run specific operations, import the helper functions:")
    print("  from examples.kerf_sdk_example import get_token, list_files, read_file")


# ----------------------------------------------------------------------
# Entry Point
# ----------------------------------------------------------------------


if __name__ == "__main__":
    run_demo()
