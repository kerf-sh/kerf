"""
Namespaced wrappers around the JSON-RPC methods exposed by /v1/rpc.

Method names match rpcMethodToTool in backend/internal/handlers/rpc.go:
  files.list, files.read, files.write, files.edit, files.create,
  files.delete, files.search, import_step, equations.read, equations.set,
  configurations.add, configurations.set_active, revisions.list,
  revisions.restore, docs.search

Heavy-op bindings (kerf.fem, kerf.cam, kerf.topo) are reserved — their
/v1/rpc methods don't exist yet. Add them here when the backend lands them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .client import Kerf


class FilesNamespace:
    def __init__(self, client: "Kerf") -> None:
        self._c = client

    def list(self, project_id: str) -> list[dict]:
        return self._c.invoke("files.list", {"project_id": project_id})

    def read(self, project_id: str, file_id: str) -> Any:
        return self._c.invoke("files.read", {"project_id": project_id, "file_id": file_id})

    def write(self, project_id: str, file_id: str, content: str) -> Any:
        return self._c.invoke("files.write", {"project_id": project_id, "file_id": file_id, "content": content})

    def edit(self, project_id: str, file_id: str, old_string: str, new_string: str) -> Any:
        return self._c.invoke("files.edit", {
            "project_id": project_id,
            "file_id": file_id,
            "old_string": old_string,
            "new_string": new_string,
        })

    def create(self, project_id: str, name: str, kind: str = "file", content: str = "", parent_id: str | None = None) -> Any:
        params: dict[str, Any] = {"project_id": project_id, "name": name, "kind": kind, "content": content}
        if parent_id is not None:
            params["parent_id"] = parent_id
        return self._c.invoke("files.create", params)

    def delete(self, project_id: str, file_id: str) -> Any:
        return self._c.invoke("files.delete", {"project_id": project_id, "file_id": file_id})

    def search(self, project_id: str, query: str) -> Any:
        return self._c.invoke("files.search", {"project_id": project_id, "query": query})


class EquationsNamespace:
    def __init__(self, client: "Kerf") -> None:
        self._c = client

    def read(self, project_id: str, file_id: str) -> Any:
        return self._c.invoke("equations.read", {"project_id": project_id, "file_id": file_id})

    def set(self, project_id: str, file_id: str, name: str, expression: str) -> Any:
        return self._c.invoke("equations.set", {
            "project_id": project_id,
            "file_id": file_id,
            "name": name,
            "expression": expression,
        })


class ConfigurationsNamespace:
    def __init__(self, client: "Kerf") -> None:
        self._c = client

    def add(self, project_id: str, file_id: str, label: str, params: dict[str, Any]) -> Any:
        return self._c.invoke("configurations.add", {
            "project_id": project_id,
            "file_id": file_id,
            "label": label,
            "params": params,
        })

    def set_active(self, project_id: str, file_id: str, config_id: str) -> Any:
        return self._c.invoke("configurations.set_active", {
            "project_id": project_id,
            "file_id": file_id,
            "config_id": config_id,
        })


class RevisionsNamespace:
    def __init__(self, client: "Kerf") -> None:
        self._c = client

    def list(self, project_id: str, file_id: str) -> Any:
        return self._c.invoke("revisions.list", {"project_id": project_id, "file_id": file_id})

    def restore(self, project_id: str, file_id: str, revision_id: str) -> Any:
        return self._c.invoke("revisions.restore", {
            "project_id": project_id,
            "file_id": file_id,
            "revision_id": revision_id,
        })


class DocsNamespace:
    def __init__(self, client: "Kerf") -> None:
        self._c = client

    def search(self, query: str) -> Any:
        return self._c.invoke("docs.search", {"query": query})
