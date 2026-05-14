"""
httpx-based JSON-RPC 2.0 client for the Kerf /v1/rpc endpoint.

Auth: Bearer kerf_sk_* token in Authorization header.
Envelope: {"jsonrpc": "2.0", "method": "...", "params": {...}, "id": "<uuid>"}
"""

import uuid
from typing import Any

import httpx


class KerfError(Exception):
    """Raised when the server returns a JSON-RPC error object."""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class Kerf:
    def __init__(self, token: str, base_url: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = httpx.Client(
            headers={"Authorization": f"Bearer {token}"},
            timeout=30.0,
        )
        from .tools import FilesNamespace, EquationsNamespace, ConfigurationsNamespace, RevisionsNamespace, DocsNamespace
        self.files = FilesNamespace(self)
        self.equations = EquationsNamespace(self)
        self.configurations = ConfigurationsNamespace(self)
        self.revisions = RevisionsNamespace(self)
        self.docs = DocsNamespace(self)

    def invoke(self, method: str, params: dict[str, Any]) -> Any:
        """Send a single JSON-RPC 2.0 call and return the result.

        Raises KerfError on a JSON-RPC error response.
        Raises httpx.HTTPStatusError on a non-2xx HTTP status.
        """
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": str(uuid.uuid4()),
        }
        resp = self._client.post(f"{self._base_url}/v1/rpc", json=payload)
        resp.raise_for_status()
        body = resp.json()
        if "error" in body and body["error"] is not None:
            err = body["error"]
            raise KerfError(err.get("code", -1), err.get("message", "unknown error"))
        return body.get("result")

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "Kerf":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()
